from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .analysis_reconciliation import procurement_analysis_integrity_snapshot


@api_view(["GET"])
def analysis_integrity(request):
    try:
        return Response(procurement_analysis_integrity_snapshot(repair=False))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
def repair_analysis_integrity(request):
    actor = getattr(request.user, "username", "") or "system"
    try:
        result = procurement_analysis_integrity_snapshot(repair=True, actor=actor)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if not result.get("repair_available"):
        return Response(
            {
                **result,
                "detail": "Active analysis run is required for automatic requeue repair.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result)
