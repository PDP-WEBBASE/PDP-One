from datetime import date, timedelta

from django.utils import timezone

from .views import ProcurementNoticeViewSet
from .views_recommended import AIRecommendedNoticeViewSet


DEADLINE_EXPIRING_DAYS = 3


def _apply_compact_browse_filters(queryset, params):
    """Apply UI-only browse filters without changing canonical notice semantics."""

    now = timezone.now()
    deadline_state = params.get("deadline_state", "").strip()
    if deadline_state == "expired":
        queryset = queryset.filter(submission_deadline__lt=now)
    elif deadline_state == "expiring":
        queryset = queryset.filter(
            submission_deadline__gte=now,
            submission_deadline__lte=now + timedelta(days=DEADLINE_EXPIRING_DAYS),
        )
    elif deadline_state == "available":
        queryset = queryset.filter(submission_deadline__gt=now + timedelta(days=DEADLINE_EXPIRING_DAYS))
    elif deadline_state == "unknown":
        queryset = queryset.filter(submission_deadline__isnull=True)

    published_on = params.get("published_on", "").strip()
    if published_on:
        try:
            selected_date = date.fromisoformat(published_on)
        except ValueError:
            selected_date = None
        if selected_date is not None:
            queryset = queryset.filter(published_date=selected_date)

    return queryset


class CompactBrowseNoticeViewSet(ProcurementNoticeViewSet):
    """Read-only notice browse view used by the compact procurement workspace."""

    def get_queryset(self):
        return _apply_compact_browse_filters(super().get_queryset(), self.request.query_params)


class CompactBrowseRecommendedNoticeViewSet(AIRecommendedNoticeViewSet):
    """Read-only effective-AI-recommendation browse view with the same compact filters."""

    def get_queryset(self):
        return _apply_compact_browse_filters(super().get_queryset(), self.request.query_params)
