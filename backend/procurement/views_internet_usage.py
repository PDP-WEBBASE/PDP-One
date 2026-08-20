from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models_analysis_runs import ProcurementAnalysisDataset
from .models_extraction import ExtractionPage, ExtractionRun


PERIODS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _dataset_size(dataset: ProcurementAnalysisDataset) -> int:
    """Return the real on-disk sizes recorded in the dataset manifest."""
    return sum(max(0, int(item.get("size_bytes") or 0)) for item in (dataset.files or []))


def _period_snapshot(since):
    extraction = ExtractionPage.objects.filter(captured_at__gte=since).aggregate(
        download_bytes=Coalesce(Sum("response_bytes"), 0),
        requests=Count("id"),
    )
    datasets = list(
        ProcurementAnalysisDataset.objects.filter(created_at__gte=since).only("files")
    )
    return {
        "download_bytes": int(extraction["download_bytes"]),
        "upload_bytes": 0,
        "known_bytes": int(extraction["download_bytes"]) + sum(_dataset_size(item) for item in datasets),
        "extraction_download_bytes": int(extraction["download_bytes"]),
        "extraction_requests": int(extraction["requests"]),
        "analysis_artifact_bytes": sum(_dataset_size(item) for item in datasets),
        "analysis_dataset_count": len(datasets),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def internet_usage_dashboard(request):
    """Read-only aggregation over byte counters already produced by normal work."""
    now = timezone.now()
    periods = {key: _period_snapshot(now - delta) for key, delta in PERIODS.items()}
    recent_runs = []
    runs = list(ExtractionRun.objects.prefetch_related("connectors").order_by("-created_at")[:20])
    run_ids = [run.id for run in runs]
    page_totals = {
        row["run_id"]: row
        for row in ExtractionPage.objects.filter(run_id__in=run_ids).values("run_id").annotate(
            measured_download_bytes=Coalesce(Sum("response_bytes"), 0),
            measured_requests=Count("id"),
        )
    }
    for run in runs:
        measured = page_totals.get(run.id, {})
        recent_runs.append({
            "id": str(run.id),
            "kind": "extraction",
            "label": "، ".join(connector.key for connector in run.connectors.all()) or "استخراج",
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "download_bytes": int(measured.get("measured_download_bytes", 0)),
            "upload_bytes": 0,
            "request_count": int(measured.get("measured_requests", 0)),
            "measurement_method": "direct_response_bytes",
        })

    return Response({
        "generated_at": now,
        "mode": "passive_read_only",
        "uses_real_data_only": True,
        "periods": periods,
        "categories": [
            {
                "key": "extraction",
                "label": "استخراج",
                "measured": True,
                "method": "direct_response_bytes",
                "description": "بایت واقعی پاسخ‌های HTTP که هنگام استخراج ثبت شده است.",
            },
            {
                "key": "analysis",
                "label": "تحلیل",
                "measured": True,
                "method": "artifact_file_size",
                "description": "اندازه واقعی فایل‌های بسته تحلیل؛ به معنی دانلود قطعی همه فایل‌ها نیست.",
            },
            {
                "key": "deployment_ci_backup_web",
                "label": "استقرار، CI، پشتیبان و کاربران وب",
                "measured": False,
                "method": "not_instrumented",
                "description": "در این نسخه عددی نمایش داده نمی‌شود تا داده تخمینی با مصرف واقعی مخلوط نشود.",
            },
        ],
        "recent_runs": recent_runs,
        "performance": {
            "hot_path_writes_added": 0,
            "packet_capture": False,
            "payload_logging": False,
            "dashboard_queries_only_when_opened": True,
        },
    })
