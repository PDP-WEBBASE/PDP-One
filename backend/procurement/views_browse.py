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


def _patch_compact_list_response(response, params):
    """Keep legacy browser predicates aligned with server-selected browse rows."""

    payload = response.data
    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return response

    source_name = params.get("source_name", "").strip()
    recent_days = params.get("recent_days", "").strip()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if source_name:
            # The queryset already proved this notice is linked to the selected
            # source. Exposing that selected source here prevents the legacy
            # client-side primary-source equality check from discarding it.
            row["source_name"] = source_name
        if recent_days and row.get("published_date"):
            # V13's legacy recent predicate reads first_seen_at. This response-
            # only compatibility value does not mutate PostgreSQL/source data.
            row["first_seen_at"] = f"{row['published_date']}T00:00:00+03:30"
    return response


class CompactBrowseNoticeViewSet(ProcurementNoticeViewSet):
    """Read-only notice browse view used by the compact procurement workspace."""

    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return _apply_compact_browse_filters(super().get_queryset(), self.request.query_params)

    def list(self, request, *args, **kwargs):
        return _patch_compact_list_response(super().list(request, *args, **kwargs), request.query_params)


class CompactBrowseRecommendedNoticeViewSet(AIRecommendedNoticeViewSet):
    """Read-only effective-AI-recommendation browse view with the same compact filters."""

    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return _apply_compact_browse_filters(super().get_queryset(), self.request.query_params)

    def list(self, request, *args, **kwargs):
        return _patch_compact_list_response(super().list(request, *args, **kwargs), request.query_params)
