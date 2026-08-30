from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .interaction_contract import (
    CAPABILITIES,
    arm_write_lease,
    confirm_pending_select_v1,
    current_revision,
    disarm_write_lease,
    prepare_pending_select_v1,
    select_notice_v1,
)
from .models_interaction import ProcurementChangeJournal
from .performance_metrics import instrument_procurement_endpoint
from .views_compact_ui import CompactNoticeSerializer, _compact_notice_queryset, _page_parameters


def _parse_optional_datetime(value: str):
    token = str(value or "").strip()
    if not token:
        return None
    parsed = parse_datetime(token)
    if parsed is None:
        raise ValueError(token)
    return parsed


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def interaction_capabilities(request):
    return Response({**CAPABILITIES, "domain_revision": current_revision()})


@instrument_procurement_endpoint("procurement.interaction.query.v1")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def query_procurement_notices(request):
    """Unified bounded procurement query contract for non-Web clients.

    This reuses the canonical compact workflow semantics but never requires a
    full-table count. One look-ahead row establishes has_more.
    """

    queryset = _compact_notice_queryset(request)

    try:
        deadline_from = _parse_optional_datetime(request.query_params.get("deadline_from", ""))
        deadline_to = _parse_optional_datetime(request.query_params.get("deadline_to", ""))
    except ValueError:
        return Response({"detail": "deadline_from/deadline_to must be ISO-8601 datetimes."}, status=status.HTTP_400_BAD_REQUEST)
    if deadline_from is not None:
        queryset = queryset.filter(submission_deadline__gte=deadline_from)
    if deadline_to is not None:
        queryset = queryset.filter(submission_deadline__lte=deadline_to)

    responsible = str(request.query_params.get("responsible", "")).strip()
    if responsible:
        queryset = queryset.filter(case__responsible__username__iexact=responsible)

    page, page_size = _page_parameters(request)
    start = (page - 1) * page_size
    rows = list(queryset[start:start + page_size + 1])
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    serializer = CompactNoticeSerializer(rows, many=True, context={"request": request})
    return Response(
        {
            "schema": "pdp-one.procurement-query.v1",
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "results": serializer.data,
            "domain_revision": current_revision(),
        }
    )


@instrument_procurement_endpoint("procurement.interaction.revision.v1")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def procurement_revision(request):
    return Response({"domain": "procurement", "revision": current_revision()})


@instrument_procurement_endpoint("procurement.interaction.changes.v1")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def procurement_changes(request):
    try:
        since = max(0, int(request.query_params.get("since", 0)))
        limit = min(max(1, int(request.query_params.get("limit", 100))), 500)
    except (TypeError, ValueError):
        return Response({"detail": "since and limit must be integers."}, status=status.HTTP_400_BAD_REQUEST)
    changes = ProcurementChangeJournal.objects.filter(domain="procurement", revision__gt=since).order_by("revision")[:limit]
    items = [
        {
            "revision": item.revision,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "action": item.action,
            "affected_contexts": item.affected_contexts,
            "correlation_id": str(item.correlation_id),
            "created_at": item.created_at,
        }
        for item in changes
    ]
    return Response(
        {
            "domain": "procurement",
            "from_revision": since,
            "current_revision": current_revision(),
            "changes": items,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def arm_procurement_write(request):
    return Response(
        arm_write_lease(
            user=request.user,
            conversation_key=request.data.get("conversation_key", ""),
            ttl_minutes=request.data.get("ttl_minutes", 60),
        )
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disarm_procurement_write(request):
    return Response(
        disarm_write_lease(user=request.user, conversation_key=request.data.get("conversation_key", ""))
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def prepare_pending_select(request):
    return Response(
        prepare_pending_select_v1(
            user=request.user,
            conversation_key=request.data.get("conversation_key", ""),
            lease_id=request.data.get("lease_id", ""),
            candidate_notice_ids=request.data.get("candidate_notice_ids", []),
            requested_text=request.data.get("requested_text", ""),
        )
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_pending_select(request):
    result = confirm_pending_select_v1(
        user=request.user,
        conversation_key=request.data.get("conversation_key", ""),
        lease_id=request.data.get("lease_id", ""),
        pending_action_id=request.data.get("pending_action_id", ""),
        notice_id=request.data.get("notice_id", ""),
    )
    return Response(result, status=status.HTTP_200_OK if result.get("verified") else status.HTTP_409_CONFLICT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def command_select_notice(request):
    result = select_notice_v1(
        user=request.user,
        conversation_key=request.data.get("conversation_key", ""),
        lease_id=request.data.get("lease_id", ""),
        notice_id=request.data.get("notice_id", ""),
    )
    return Response(result, status=status.HTTP_200_OK if result.get("verified") else status.HTTP_409_CONFLICT)
