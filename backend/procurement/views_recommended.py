from datetime import date

from django.db.models import BooleanField, Case, Count, DateField, F, Subquery, Value, When, Window
from django.db.models.functions import Coalesce, RowNumber
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import AuditEvent

from .models import ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .serializers import ProcurementNoticeListSerializer
from .views import _filter_deadline_urgency


class AIRecommendedNoticeSerializer(ProcurementNoticeListSerializer):
    """Serialize the effective recommendation represented by this filtered view."""

    is_recommended = serializers.SerializerMethodField()

    def get_is_recommended(self, obj):
        return True


def latest_effective_recommended_notice_ids():
    """Return notice IDs whose latest analysis draft is effectively recommended.

    Rank the comparatively small draft table once, then join the resulting notice
    IDs back to ProcurementNotice. This avoids the former correlated subquery over
    every notice while preserving the exact latest-draft / rejected-draft rule.
    """

    return (
        NoticeAnalysisDraft.objects.annotate(
            recommendation_rank=Window(
                expression=RowNumber(),
                partition_by=[F("notice_id")],
                order_by=[F("analyzed_at").desc(), F("created_at").desc(), F("id").desc()],
            ),
            effective_recommendation=Case(
                When(
                    review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED,
                    then=Value(False),
                ),
                default=F("is_recommended"),
                output_field=BooleanField(),
            ),
        )
        .filter(recommendation_rank=1, effective_recommendation=True)
        .values("notice_id")
    )


class AIRecommendedNoticeViewSet(viewsets.ReadOnlyModelViewSet):
    """Return notices whose latest valid ChatGPT analysis recommends them."""

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
    filterset_fields = ["resolved_notice_type", "province", "employer_name", "importance"]
    ordering_fields = [
        "publication_sort",
        "published_date",
        "submission_deadline",
        "first_seen_at",
        "last_seen_at",
        "created_at",
        "id",
    ]
    ordering = ["-publication_sort", "-last_seen_at", "-id"]

    def get_queryset(self):
        queryset = (
            ProcurementNotice.objects.filter(
                soft_deleted_at__isnull=True,
                is_hidden=False,
                pk__in=Subquery(latest_effective_recommended_notice_ids()),
            )
            .select_related("case", "case__responsible", "reference_record")
            .prefetch_related("source_links__source_notice__connector__source")
            .annotate(
                source_count=Count("source_links", distinct=True),
                publication_sort=Coalesce(
                    "published_date",
                    Value(date(1900, 1, 1)),
                    output_field=DateField(),
                ),
            )
        )
        params = self.request.query_params
        if params.get("actionable", "").lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(case__isnull=True)

        source_name = params.get("source_name", "").strip()
        if source_name:
            queryset = queryset.filter(
                source_links__source_notice__connector__source__name=source_name
            )

        queryset = _filter_deadline_urgency(
            queryset,
            "submission_deadline",
            params.get("urgency", "").strip(),
        )
        return queryset

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
