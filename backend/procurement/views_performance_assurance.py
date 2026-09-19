from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_run_service import active_run
from .performance_metrics import performance_assurance_snapshot


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def performance_assurance_report(request):
    """Return sanitized low-overhead runtime performance evidence.

    This endpoint never executes stress traffic, EXPLAIN ANALYZE, arbitrary SQL,
    or a full-table diagnostic scan. It summarizes telemetry already collected
    while normal interactive requests execute.
    """

    run = active_run()
    background = {
        "analysis_active": bool(run),
        "analysis_run_id": str(run.id) if run else None,
        "analysis_status": run.status if run else None,
    }
    if run is not None:
        counters = run.counters or {}
        background["analysis_remaining"] = int(counters.get("remaining", 0) or 0)
        background["analysis_imported"] = int(counters.get("imported", 0) or 0)

    payload = performance_assurance_snapshot(compact=False)
    payload["background_workload"] = background
    return Response(payload)
