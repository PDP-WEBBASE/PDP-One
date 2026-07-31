from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .analysis_review import analysis_review_summary
from .models import ProcurementCase, ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .serializers import ProcurementCaseSerializer
from .serializers_review import AIReviewDraftSerializer


def _staff_required(request):
    if not request.user or not request.user.is_authenticated or not request.user.is_staff:
        return Response({"detail": "این اقدام فقط برای مدیر سامانه مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    return None


class AIReviewDraftViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = NoticeAnalysisDraft.objects.select_related(
        "notice",
        "notice__case",
        "notice__case__responsible",
        "batch",
        "context_snapshot",
    ).all()
    serializer_class = AIReviewDraftSerializer
    filterset_fields = [
        "notice",
        "batch",
        "context_snapshot",
        "is_recommended",
        "priority",
        "review_status",
    ]
    search_fields = [
        "notice__title",
        "notice__employer_name",
        "category",
        "fit_for_pdp",
        "reason",
        "recommended_action",
    ]
    ordering_fields = ["analyzed_at", "score", "confidence", "created_at"]
    ordering = ["-analyzed_at"]

    def get_serializer_class(self):
        if self.action == "create":
            from .serializers_analysis import NoticeAnalysisDraftSerializer

            return NoticeAnalysisDraftSerializer
        return AIReviewDraftSerializer

    def perform_create(self, serializer):
        draft = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.notice_analysis.create_draft",
            target_type="notice_analysis_draft",
            target_id=str(draft.id),
            payload={
                "notice_id": str(draft.notice_id),
                "batch_id": str(draft.batch_id),
                "context_version": draft.context_snapshot.version,
                "recommended": draft.is_recommended,
            },
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_review_summary_view(request):
    return Response(analysis_review_summary())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def review_analysis_draft(request, draft_id):
    denied = _staff_required(request)
    if denied:
        return denied

    draft = get_object_or_404(
        NoticeAnalysisDraft.objects.select_related("notice", "notice__case"),
        pk=draft_id,
    )
    requested_status = str(request.data.get("review_status", "")).strip()
    requested_decision = str(request.data.get("decision", "")).strip()
    note = str(request.data.get("note", "")).strip()[:1000]

    status_to_decision = {
        NoticeAnalysisDraft.ReviewStatus.REVIEWED: "approved",
        NoticeAnalysisDraft.ReviewStatus.PUBLISHED: "published",
        NoticeAnalysisDraft.ReviewStatus.REJECTED: "rejected",
    }
    decision = requested_decision or status_to_decision.get(requested_status, "")
    decision_to_status = {
        "approved": NoticeAnalysisDraft.ReviewStatus.REVIEWED,
        "published": NoticeAnalysisDraft.ReviewStatus.PUBLISHED,
        "rejected": NoticeAnalysisDraft.ReviewStatus.REJECTED,
        "needs_revision": NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
    }
    if decision not in decision_to_status:
        return Response({"detail": "تصمیم بازبینی نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
    if decision in {"rejected", "needs_revision"} and not note:
        return Response({"detail": "برای رد یا بازگشت جهت تکمیل، ثبت توضیح الزامی است."}, status=status.HTTP_400_BAD_REQUEST)

    before_status = draft.review_status
    draft.review_status = decision_to_status[decision]
    raw_output = dict(draft.raw_output or {})
    raw_output["human_review"] = {
        "decision": decision,
        "note": note,
        "reviewed_by": request.user.username,
        "reviewed_at": timezone.now().isoformat(),
    }
    draft.raw_output = raw_output
    draft.save(update_fields=["review_status", "raw_output", "updated_at"])

    if decision == "rejected":
        draft.notice.is_recommended = False
    elif decision in {"approved", "published"}:
        draft.notice.is_recommended = draft.is_recommended
    draft.notice.save(update_fields=["is_recommended", "updated_at"])

    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.notice_analysis.review",
        target_type="notice_analysis_draft",
        target_id=str(draft.id),
        payload={
            "notice_id": str(draft.notice_id),
            "status_before": before_status,
            "status_after": draft.review_status,
            "decision": decision,
            "note": note,
            "is_recommended": draft.is_recommended,
        },
    )
    return Response(AIReviewDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def select_reviewed_analysis_draft(request, draft_id):
    denied = _staff_required(request)
    if denied:
        return denied

    draft = get_object_or_404(
        NoticeAnalysisDraft.objects.select_related("notice", "notice__case"),
        pk=draft_id,
    )
    if not draft.is_recommended:
        return Response({"detail": "فقط تحلیل پیشنهادی قابل تبدیل به پرونده منتخب است."}, status=status.HTTP_409_CONFLICT)
    if draft.review_status not in {
        NoticeAnalysisDraft.ReviewStatus.REVIEWED,
        NoticeAnalysisDraft.ReviewStatus.PUBLISHED,
    }:
        return Response({"detail": "ابتدا تحلیل باید توسط انسان تأیید شود."}, status=status.HTTP_409_CONFLICT)

    case, created = ProcurementCase.objects.get_or_create(
        notice=draft.notice,
        defaults={
            "stage": ProcurementCase.Stage.SELECTED,
            "created_by": request.user,
            "protected_from_retention": True,
            "next_action": "بررسی اسناد و تصمیم‌گیری درباره شرکت یا پاسخ",
        },
    )
    ProcurementNotice.objects.filter(pk=draft.notice_id).update(retention_protected=True)
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.notice_analysis.select_for_followup",
        target_type="procurement_case",
        target_id=str(case.id),
        payload={
            "analysis_draft_id": str(draft.id),
            "notice_id": str(draft.notice_id),
            "created": created,
            "stage": case.stage,
        },
    )
    draft = NoticeAnalysisDraft.objects.select_related(
        "notice", "notice__case", "notice__case__responsible", "batch", "context_snapshot"
    ).get(pk=draft.pk)
    return Response(
        {
            "created": created,
            "case": ProcurementCaseSerializer(case).data,
            "draft": AIReviewDraftSerializer(draft).data,
            "requires_human_follow_up": True,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
