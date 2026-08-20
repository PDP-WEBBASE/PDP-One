from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models_analysis_runs import ProcurementAnalysisDataset
from .models_extraction import ExtractionPage


PERIODS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "all": None,
}


def _dataset_size(dataset: ProcurementAnalysisDataset) -> int:
    """Return the real on-disk sizes recorded in the dataset manifest."""
    return sum(max(0, int(item.get("size_bytes") or 0)) for item in (dataset.files or []))


def _period_snapshot(since):
    extraction_pages = ExtractionPage.objects.all()
    datasets_query = ProcurementAnalysisDataset.objects.all()
    if since is not None:
        extraction_pages = extraction_pages.filter(captured_at__gte=since)
        datasets_query = datasets_query.filter(created_at__gte=since)
    extraction = extraction_pages.aggregate(
        download_bytes=Coalesce(Sum("response_bytes"), 0),
        requests=Count("id"),
    )
    datasets = list(datasets_query.only("files"))
    analysis_bytes = sum(_dataset_size(item) for item in datasets)
    return {
        "extraction": {
            "download_bytes": int(extraction["download_bytes"]),
            "upload_bytes": None,
            "total_bytes": int(extraction["download_bytes"]),
            "operation_count": int(extraction["requests"]),
        },
        "analysis": {
            "download_bytes": None,
            "upload_bytes": analysis_bytes,
            "total_bytes": analysis_bytes,
            "operation_count": len(datasets),
        },
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def internet_usage_dashboard(request):
    """Read-only aggregation over byte counters already produced by normal work."""
    now = timezone.now()
    periods = {
        key: _period_snapshot(None if delta is None else now - delta)
        for key, delta in PERIODS.items()
    }
    all_measured = sum(periods["all"][key]["total_bytes"] for key in ("extraction", "analysis"))

    def activity(key, label, measured, method, description):
        values = {
            period: periods[period].get(key, {
                "download_bytes": None,
                "upload_bytes": None,
                "total_bytes": None,
                "operation_count": None,
            })
            for period in PERIODS
        }
        total = values["all"]["total_bytes"]
        return {
            "key": key,
            "label": label,
            "measured": measured,
            "method": method,
            "description": description,
            "periods": values,
            "share_percent": round((total / all_measured) * 100, 2) if measured and all_measured and total is not None else None,
        }

    activities = [
        activity("extraction", "استخراج آگهی‌ها", True, "direct_response_bytes", "دانلود مستقیم ثبت‌شده در پاسخ‌های HTTP استخراج."),
        activity("analysis", "تحلیل با ChatGPT", True, "artifact_file_size", "اندازه واقعی بسته‌های تحلیل آماده ارسال؛ انتقال قطعی همه فایل‌ها را اثبات نمی‌کند."),
        activity("ci_images", "CI و ساخت Image", False, "not_instrumented", "اندازه‌گیری واقعی این فعالیت هنوز به سامانه متصل نشده است."),
        activity("deployment", "Deploy", False, "not_instrumented", "اندازه‌گیری واقعی این فعالیت هنوز به سامانه متصل نشده است."),
        activity("backup", "Backup", False, "not_instrumented", "اندازه‌گیری واقعی این فعالیت هنوز به سامانه متصل نشده است."),
        activity("web_users", "کاربران وب", False, "not_instrumented", "اندازه‌گیری واقعی این فعالیت هنوز به سامانه متصل نشده است."),
        activity("unknown", "سایر / نامشخص", False, "not_instrumented", "تا اتصال شمارنده کل شبکه، اختلاف مصرف قابل محاسبه نیست."),
    ]

    return Response({
        "generated_at": now,
        "mode": "passive_read_only",
        "uses_real_data_only": True,
        "activities": activities,
        "measured_totals": {
            period: sum(periods[period][key]["total_bytes"] for key in ("extraction", "analysis"))
            for period in PERIODS
        },
        "performance": {
            "hot_path_writes_added": 0,
            "packet_capture": False,
            "payload_logging": False,
            "dashboard_queries_only_when_opened": True,
        },
    })
