from django.db.models import BooleanField, Case, Count, F, OuterRef, Subquery, Value, When
from rest_framework import serializers, viewsets

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
