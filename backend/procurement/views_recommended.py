from django.db.models import BooleanField, Case, Count, F, OuterRef, Subquery, Value, When
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import AuditEvent

from .models import ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .serializers import ProcurementNoticeListSerializer


class AIRecommendedNoticeSerializer(ProcurementNoticeListSerializer):
    """Serialize the recommendation flag from the latest effective ChatGPT draft."""

    is_recommended = serializers.SerializerMethodField()

    def get_is_recommended(self, obj):
        return bool(getattr(obj, "ai_is_recommended", False))


class AIRecommendedNoticeViewSet(viewsets.ReadOnlyModelViewSet):
    """Return only notices whose latest valid ChatGPT analysis recommends them.

    This intentionally does not trust ProcurementNotice.is_recommended because that
    compatibility flag can be stale after historical imports or older workflows.
    The latest NoticeAnalysisDraft is the source of truth for this view.
    """

    serializer_class = AIRecommendedNoticeSerializer
    search_fields = [
        "reference_record__code",
        "title",
        "normalized_title",
        "summary",
        "description",
        "employer_name",
        "notice_number",
        "province",
        "city",
    ]
    filterset_fields = ["resolved_notice_type", "province", "employer_name"]
    ordering_fields = [
        "published_date",
        "submission_deadline",
        "first_seen_at",
        "last_seen_at",
        "created_at",
    ]
    ordering = ["-last_seen_at"]

    def get_queryset(self):
        latest_effective_recommendation = (
            NoticeAnalysisDraft.objects.filter(notice_id=OuterRef("pk"))
            .annotate(
                effective_recommendation=Case(
                    When(
                        review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED,
                        then=Value(False),
                    ),
                    default=F("is_recommended"),
                    output_field=BooleanField(),
                )
            )
            .order_by("-analyzed_at", "-created_at", "-id")
            .values("effective_recommendation")[:1]
        )
        return (
            ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
            .select_related("case", "case__responsible", "reference_record")
            .prefetch_related("source_links__source_notice__connector__source")
            .annotate(
                source_count=Count("source_links", distinct=True),
                ai_is_recommended=Subquery(
                    latest_effective_recommendation,
                    output_field=BooleanField(),
                ),
            )
            .filter(ai_is_recommended=True)
        )

    @action(detail=True, methods=["post"], url_path="dismiss")
    def dismiss_recommendation(self, request, pk=None):
        """Record a human rejection of the current AI recommendation without deleting the notice."""

        notice = self.get_object()
        draft = (
            NoticeAnalysisDraft.objects.filter(notice=notice)
            .order_by("-analyzed_at", "-created_at", "-id")
            .first()
        )
        if draft is None:
            return Response(
                {"detail": "تحلیل فعالی برای این پیشنهاد پیدا نشد."},
                status=status.HTTP_409_CONFLICT,
            )

        previous_status = draft.review_status
        draft.review_status = NoticeAnalysisDraft.ReviewStatus.REJECTED
        draft.save(update_fields=["review_status", "updated_at"])
        ProcurementNotice.objects.filter(pk=notice.pk).update(is_recommended=False)

        reason = str(request.data.get("reason", "")).strip()[:500]
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.ai_recommendation.dismiss",
            target_type="procurement_notice",
            target_id=str(notice.id),
            payload={
                "analysis_draft_id": str(draft.id),
                "review_status_before": previous_status,
                "review_status_after": draft.review_status,
                "notice_deleted": False,
                "reason": reason,
            },
        )
        return Response(
            {
                "dismissed": True,
                "notice_id": str(notice.id),
                "analysis_draft_id": str(draft.id),
                "notice_deleted": False,
            }
        )
