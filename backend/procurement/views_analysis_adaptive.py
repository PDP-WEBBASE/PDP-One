from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_run_adaptive import admit_newest_pending_items, claim_newest_run_items, renew_worker_claim
from .analysis_run_service import serialize_claimed_items


def _allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


def _actor(request) -> str:
    return getattr(request.user, "username", "") or "unknown"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_analysis_work_adaptive(request, run_id):
    if not _allowed(request.user):
        return Response(
            {"detail": "این عملیات فقط برای مدیر سامانه یا سرویس رسمی ChatGPT مجاز است."},
            status=status.HTTP_403_FORBIDDEN,
        )
    worker_id = str(request.data.get("worker_id") or _actor(request))
    lease_seconds = int(request.data.get("lease_seconds") or 3600)
    try:
        if bool(request.data.get("renew_only", False)):
            return Response(
                {
                    **renew_worker_claim(
                        str(run_id),
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                        actor=_actor(request),
                    ),
                    "renew_only": True,
                    "decision_is_draft": True,
                    "requires_human_review": True,
                }
            )

        admission = admit_newest_pending_items(str(run_id), actor=_actor(request))
        items = claim_newest_run_items(
            str(run_id),
            worker_id=worker_id,
            limit=int(request.data.get("limit") or 500),
            lease_seconds=lease_seconds,
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

    compact_payload = serialize_claimed_items(items)
    return Response(
        {
            "run_id": str(run_id),
            "count": len(items),
            **compact_payload,
            "priority_policy": "newest_first",
            "fresh_items_admitted": int(admission.get("admitted", 0)),
            "decision_is_draft": True,
            "requires_human_review": True,
        }
    )
