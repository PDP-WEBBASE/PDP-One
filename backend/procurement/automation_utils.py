from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from .models_automation import ProcurementAutomationSettings


def calculate_next_extraction(settings: ProcurementAutomationSettings, *, now=None):
    now = now or timezone.now()
    if not settings.enabled:
        return None
    if settings.cadence == ProcurementAutomationSettings.Cadence.HOURLY:
        return now + timedelta(minutes=max(settings.interval_minutes, 60))
    if settings.daily_time is None:
        return None
    try:
        local_zone = ZoneInfo(settings.timezone_name)
    except ZoneInfoNotFoundError:
        local_zone = ZoneInfo("Asia/Tehran")
    local_now = now.astimezone(local_zone)
    local_target = datetime.combine(local_now.date(), settings.daily_time, tzinfo=local_zone)
    if local_target <= local_now:
        local_target += timedelta(days=1)
    return local_target.astimezone(timezone.get_current_timezone())


def analysis_eligible_at(extraction_finished_at, delay_minutes: int):
    if extraction_finished_at is None:
        return None
    return extraction_finished_at + timedelta(minutes=max(delay_minutes, 0))
