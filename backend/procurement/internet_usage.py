from django.utils import timezone

from .models_internet_usage import InternetUsageEvent


def record_internet_usage(*, activity: str, source: str, download_bytes: int = 0, upload_bytes: int = 0, operation_count: int = 1, reference: str = "") -> InternetUsageEvent:
    """Record metadata-only counters; payloads and URLs are never stored."""
    valid_activities = {value for value, _ in InternetUsageEvent.Activity.choices}
    if activity not in valid_activities:
        raise ValueError("Unsupported internet usage activity.")
    if int(download_bytes) < 0 or int(upload_bytes) < 0:
        raise ValueError("Byte counters cannot be negative.")
    if int(operation_count) < 1:
        raise ValueError("Operation count must be at least one.")
    return InternetUsageEvent.objects.create(
        activity=activity,
        source=str(source).strip()[:64] or "unspecified",
        download_bytes=int(download_bytes),
        upload_bytes=int(upload_bytes),
        operation_count=int(operation_count),
        occurred_at=timezone.now(),
        reference=str(reference)[:160],
    )
