from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_run_service import active_run, refresh_run_counters
from .analysis_statistics import procurement_analysis_statistics
from .models_analysis_runs import ProcurementAnalysisRun
from .serializers_analysis_runs import ProcurementAnalysisRunSerializer
from .views_analysis_runs import _deny


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_analysis_run_with_statistics(request):
    """Preserve the existing current-run contract and append exact split statistics."""

    denied = _deny(request)
    if denied:
        return denied
    run = active_run()
    if run is None:
        return Response({"run": None, "statistics": procurement_analysis_statistics(None)})
    refresh_run_counters(run)
    run.refresh_from_db()
    return Response(
        {
            "run": ProcurementAnalysisRunSerializer(run).data,
            "statistics": procurement_analysis_statistics(run),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_run_status_with_statistics(request, run_id):
    """Preserve the existing run-status contract and append exact split statistics."""

    denied = _deny(request)
    if denied:
        return denied
    run = get_object_or_404(
        ProcurementAnalysisRun.objects.select_related("context_snapshot", "requested_by"),
        pk=run_id,
    )
    refresh_run_counters(run)
    run.refresh_from_db()
    return Response(
        {
            "run": ProcurementAnalysisRunSerializer(run).data,
            "statistics": procurement_analysis_statistics(run),
        }
    )
