from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .analysis_reconciliation import procurement_analysis_integrity_snapshot


def _sanitized_execution_error(exc: Exception) -> Response:
    return Response(
        {
            "detail": "Procurement analysis integrity execution failed.",
            "error_code": "analysis_integrity_execution_failed",
            "error_type": type(exc).__name__,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@api_view(["GET"])
def analysis_integrity(request):
    try:
        return Response(procurement_analysis_integrity_snapshot(repair=False))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    except Exception as exc:
        return _sanitized_execution_error(exc)


@api_view(["POST"])
def repair_analysis_integrity(request):
    actor = getattr(request.user, "username", "") or "system"
    try:
        result = procurement_analysis_integrity_snapshot(repair=True, actor=actor)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    except Exception as exc:
        return _sanitized_execution_error(exc)
    if not result.get("repair_available"):
        return Response(
            {
                **result,
                "detail": "Active analysis run is required for automatic requeue repair.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result)
