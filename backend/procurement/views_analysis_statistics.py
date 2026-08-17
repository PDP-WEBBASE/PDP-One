from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_run_service import active_run
from .analysis_statistics import procurement_analysis_statistics
from .models_analysis_runs import ProcurementAnalysisRun


def _allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_statistics(request):
    if not _allowed(request.user):
        return Response(
            {"detail": "این گزارش فقط برای مدیر سامانه یا سرویس رسمی ChatGPT مجاز است."},
            status=status.HTTP_403_FORBIDDEN,
        )

    run_id = str(request.query_params.get("run_id") or "").strip()
    if run_id:
        try:
            run = ProcurementAnalysisRun.objects.get(pk=run_id)
        except (ProcurementAnalysisRun.DoesNotExist, ValueError):
            return Response({"detail": "Run تحلیل پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)
    else:
        run = active_run()
    return Response(procurement_analysis_statistics(run))
