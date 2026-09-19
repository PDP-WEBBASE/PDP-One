from hashlib import sha256

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .interaction_contract import current_revision
from .performance_metrics import instrument_procurement_endpoint
from .views_bulk_workflow import VIEW_DISMISS_WORKFLOWS, _user_dismissed_notice_ids
from .views_compact_ui import _compact_notice_queryset


EXACT_PAGINATION_COUNT_TTL_SECONDS = 30


def _exact_pagination_cache_key(request, revision: int) -> str:
    excluded = {"page", "page_size", "ordering"}
    normalized = []
    for key in sorted(request.query_params.keys()):
        if key in excluded:
            continue
        values = sorted(str(value) for value in request.query_params.getlist(key))
        normalized.append((key, values))
    fingerprint = sha256(repr(normalized).encode("utf-8")).hexdigest()
    return f"procurement:exact-pagination:{request.user.pk}:{revision}:{fingerprint}"


@instrument_procurement_endpoint("procurement.ui.notices.pagination-metadata.v1")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exact_notice_pagination_metadata(request):
    """Return exact pagination totals outside the bounded notice-feed hot path."""

    queryset = _compact_notice_queryset(request)
    workflow = str(request.query_params.get("workflow", "recent")).strip() or "recent"
    if workflow in VIEW_DISMISS_WORKFLOWS:
        dismissed_ids = _user_dismissed_notice_ids(request, workflow)
        if dismissed_ids:
            queryset = queryset.exclude(pk__in=dismissed_ids)

    revision = current_revision()
    cache_key = _exact_pagination_cache_key(request, revision)
    total_count = cache.get(cache_key)
    cache_hit = total_count is not None
    if total_count is None:
        total_count = queryset.count()
        cache.set(cache_key, total_count, EXACT_PAGINATION_COUNT_TTL_SECONDS)

    return Response(
        {
            "total_count": int(total_count),
            "count_is_exact": True,
            "domain_revision": revision,
            "cache_hit": cache_hit,
        }
    )
