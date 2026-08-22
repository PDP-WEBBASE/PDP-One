from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models_extraction import ExtractionPage
from .models_internet_usage import InternetUsageEvent


PERIODS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "all": None}
EVENT_ACTIVITIES = {choice for choice, _ in InternetUsageEvent.Activity.choices}


def _event_snapshot(activity, since):
    query = InternetUsageEvent.objects.filter(activity=activity)
    if since is not None:
        query = query.filter(occurred_at__gte=since)
    result = query.aggregate(
        download_bytes=Coalesce(Sum("download_bytes"), 0),
        upload_bytes=Coalesce(Sum("upload_bytes"), 0),
        operation_count=Coalesce(Sum("operation_count"), 0),
        rows=Count("id"),
    )
    return {
        "download_bytes": int(result["download_bytes"]),
        "upload_bytes": int(result["upload_bytes"]),
        "total_bytes": int(result["download_bytes"]) + int(result["upload_bytes"]),
        "operation_count": int(result["operation_count"]),
        "event_count": int(result["rows"]),
    }


def _period_snapshot(since):
    extraction_pages = ExtractionPage.objects.all()
    if since is not None:
        extraction_pages = extraction_pages.filter(captured_at__gte=since)
    extraction = extraction_pages.aggregate(download_bytes=Coalesce(Sum("response_bytes"), 0), requests=Count("id"))
    values = {
        "extraction": {
            "download_bytes": int(extraction["download_bytes"]),
            "upload_bytes": 0,
            "total_bytes": int(extraction["download_bytes"]),
            "operation_count": int(extraction["requests"]),
            "event_count": int(extraction["requests"]),
        }
    }
    values.update({activity: _event_snapshot(activity, since) for activity in EVENT_ACTIVITIES})
    return values


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def internet_usage_dashboard(request):
    """Read-only aggregation over metadata-only counters from completed transfers."""
    now = timezone.now()
    periods = {key: _period_snapshot(None if delta is None else now - delta) for key, delta in PERIODS.items()}
    definitions = [
        ("extraction", "استخراج آگهی‌ها", True, "direct_response_bytes", "دانلود واقعی پاسخ‌های HTTP استخراج؛ درخواست‌های بدون بدنه، آپلود صفر دارند."),
        ("analysis", "تحلیل با ChatGPT", True, "completed_transfer_bytes", "فقط انتقال کامل Dataset و ورود واقعی فایل/JSON نتیجه از زمان فعال‌شدن شمارنده."),
        ("ci_images", "CI و ساخت Image", False, "event_meter", "رویدادهای انتقال ثبت‌شده CI/Image؛ اجرای ابری GitHub مصرف اینترنت میزبان نیست."),
        ("deployment", "Deploy", False, "event_meter", "رویدادهای انتقال ثبت‌شده Deploy؛ تا اتصال گزارش Pull مقدار نمایش داده نمی‌شود."),
        ("backup", "Backup", False, "event_meter", "فقط انتقال واقعی Backup؛ ساخت یا کپی محلی مصرف اینترنت محسوب نمی‌شود."),
        ("web_users", "کاربران وب", False, "aggregate_web_meter", "شمارنده تجمیعی وب هنوز فعال نشده تا Hot Path نوشتن پایگاه داده نداشته باشد."),
        ("unknown", "سایر / نامشخص", False, "host_counter_delta", "پس از اتصال نمونه‌بردار پنج‌دقیقه‌ای کارت شبکه از اختلاف کل محاسبه می‌شود."),
    ]
    activities = []
    for key, label, instrumented, method, description in definitions:
        values = {period: periods[period][key] for period in PERIODS}
        has_coverage = instrumented or values["all"].get("event_count", 0) > 0
        if not has_coverage:
            values = {period: {"download_bytes": None, "upload_bytes": None, "total_bytes": None, "operation_count": None} for period in PERIODS}
        activities.append({"key": key, "label": label, "measured": has_coverage, "method": method, "description": description, "periods": values, "share_percent": None})
    all_measured = sum(item["periods"]["all"]["total_bytes"] or 0 for item in activities if item["measured"])
    for item in activities:
        total = item["periods"]["all"]["total_bytes"]
        item["share_percent"] = round((total / all_measured) * 100, 2) if item["measured"] and all_measured and total is not None else None
    return Response({
        "generated_at": now,
        "mode": "passive_read_only",
        "uses_real_data_only": True,
        "activities": activities,
        "measured_totals": {period: sum(item["periods"][period]["total_bytes"] or 0 for item in activities if item["measured"]) for period in PERIODS},
        "coverage": {"historical_complete": False, "payload_logging": False, "packet_capture": False},
        "performance": {"hot_path_writes_added": 0, "packet_capture": False, "payload_logging": False, "dashboard_queries_only_when_opened": True},
    })
