from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .analysis_workflow import finish_analysis_request, normalize_limit, serialize_work, start_analysis_request
from .models_analysis import AnalysisRequest, NoticeAnalysisDraft
from .serializers_analysis import (
    AnalysisBatchSerializer,
    AnalysisContextSnapshotSerializer,
    AnalysisRequestSerializer,
    NoticeAnalysisDraftSerializer,
)


def _engine_allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


def _staff_required(request):
    if not request.user or not request.user.is_authenticated or not request.user.is_staff:
        return Response({"detail": "این اقدام فقط برای مدیر سامانه مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_analysis_engine(request):
    if not _engine_allowed(request.user):
        return Response({"detail": "شروع موتور تحلیل فقط برای مدیر یا سرویس ChatGPT مجاز است."}, status=status.HTTP_403_FORBIDDEN)

    serializer = AnalysisRequestSerializer(
        data={
            "trigger": request.data.get("trigger", AnalysisRequest.Trigger.MANUAL_WEB),
            "extraction_run": request.data.get("extraction_run"),
            "eligible_after": request.data.get("eligible_after"),
            "metadata": request.data.get("metadata", {}),
        },
        context={
            "request": request,
            "allow_scheduled": getattr(request.user, "username", "") == "chatgpt-service",
        },
    )
    serializer.is_valid(raise_exception=True)
    analysis_request = serializer.save()
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.analysis_request.create",
        target_type="analysis_request",
        target_id=str(analysis_request.id),
        payload={
            "trigger": analysis_request.trigger,
            "command": "PDP",
            "context_version": analysis_request.context_snapshot.version,
            "extraction_run": str(analysis_request.extraction_run_id or ""),
        },
    )

    try:
        analysis_request, batch = start_analysis_request(
            analysis_request,
            limit=normalize_limit(request.data.get("limit")),
            actor=request.user.username,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

    payload = {
        "request": AnalysisRequestSerializer(analysis_request).data,
        "batch": AnalysisBatchSerializer(batch).data if batch else None,
        "work_count": batch.item_count if batch else 0,
        "command": "PDP",
        "requires_chatgpt_processing": batch is not None,
        "requires_human_review": True,
    }
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_engine_work(request, request_id):
    if not _engine_allowed(request.user):
        return Response({"detail": "دریافت بسته تحلیل فقط برای مدیر یا سرویس ChatGPT مجاز است."}, status=status.HTTP_403_FORBIDDEN)

    analysis_request = get_object_or_404(
        AnalysisRequest.objects.select_related("context_snapshot", "extraction_run", "requested_by"),
        pk=request_id,
    )
    if analysis_request.status not in {AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING}:
        return Response(
            {"detail": "این درخواست بسته کار فعالی ندارد.", "status": analysis_request.status},
            status=status.HTTP_409_CONFLICT,
        )
    limit = normalize_limit(request.query_params.get("limit"), default=10)
    items = serialize_work(analysis_request, limit=limit)
    batch = analysis_request.batches.order_by("-sequence").first()
    return Response(
        {
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data if batch else None,
            "context": AnalysisContextSnapshotSerializer(analysis_request.context_snapshot).data,
            "count": len(items),
            "items": items,
            "output_contract": {
                "required_fields": [
                    "notice_id",
                    "batch_id",
                    "is_recommended",
                    "score",
                    "priority",
                    "fit_for_pdp",
                    "category",
                    "reason",
                    "recommended_action",
                    "matched_experience",
                    "risk_notes",
                    "confidence",
                ],
                "score_range": [0, 100],
                "priority_values": ["low", "medium", "high", "urgent"],
                "decision_is_draft": True,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def finish_analysis_engine(request, request_id):
    if not _engine_allowed(request.user):
        return Response({"detail": "پایان موتور تحلیل فقط برای مدیر یا سرویس ChatGPT مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    analysis_request = get_object_or_404(AnalysisRequest, pk=request_id)
    try:
        analysis_request, batch = finish_analysis_request(
            analysis_request,
            actor=request.user.username,
            failed_notice_ids=request.data.get("failed_notice_ids") or [],
            summary=request.data.get("summary") or {},
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(
        {
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data if batch else None,
            "requires_human_review": True,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_analysis_draft(request, draft_id):
    denied = _staff_required(request)
    if denied:
        return denied
    draft = get_object_or_404(NoticeAnalysisDraft.objects.select_related("notice"), pk=draft_id)
    requested_status = str(request.data.get("review_status", "")).strip()
    allowed = {
        NoticeAnalysisDraft.ReviewStatus.REVIEWED,
        NoticeAnalysisDraft.ReviewStatus.PUBLISHED,
        NoticeAnalysisDraft.ReviewStatus.REJECTED,
    }
    if requested_status not in allowed:
        return Response({"detail": "وضعیت بازبینی نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)

    draft.review_status = requested_status
    draft.save(update_fields=["review_status", "updated_at"])
    if requested_status == NoticeAnalysisDraft.ReviewStatus.REJECTED:
        draft.notice.is_recommended = False
        draft.notice.save(update_fields=["is_recommended", "updated_at"])
    elif requested_status == NoticeAnalysisDraft.ReviewStatus.PUBLISHED:
        draft.notice.is_recommended = draft.is_recommended
        draft.notice.save(update_fields=["is_recommended", "updated_at"])

    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.notice_analysis.review",
        target_type="notice_analysis_draft",
        target_id=str(draft.id),
        payload={
            "notice_id": str(draft.notice_id),
            "review_status": requested_status,
            "is_recommended": draft.is_recommended,
        },
    )
    return Response(NoticeAnalysisDraftSerializer(draft).data)
