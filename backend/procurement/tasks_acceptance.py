from datetime import timedelta

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from django.utils import timezone

from .models_extraction import ExtractionError, ExtractionRun
from .tasks import run_extraction

ACTIVE_STATUSES = (ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING)


def repair_stale_extraction_runs(*, max_age_minutes: int = 60) -> dict:
    """Close orphaned extraction runs without deleting any captured data."""
    minutes = max(15, min(int(max_age_minutes), 24 * 60))
    now = timezone.now()
    cutoff = now - timedelta(minutes=minutes)
    stale_runs = list(
        ExtractionRun.objects.filter(status__in=ACTIVE_STATUSES, updated_at__lt=cutoff)
        .prefetch_related("connectors")
        .order_by("created_at")
    )
    repaired_ids: list[str] = []
    for run in stale_runs:
        previous_status = run.status
        summary = dict(run.summary or {})
        summary["watchdog"] = {
            "repaired_at": now.isoformat(),
            "previous_status": previous_status,
            "reason": "stale_extraction_run",
            "max_age_minutes": minutes,
            "captured_data_preserved": True,
        }
        run.status = ExtractionRun.Status.FAILED
        run.finished_at = now
        run.summary = summary
        run.save(update_fields=["status", "finished_at", "summary", "updated_at"])
        for connector in run.connectors.all():
            ExtractionError.objects.create(
                run=run,
                connector=connector,
                category=ExtractionError.Category.UNEXPECTED,
                safe_message="اجرای استخراج بدون پایان معتبر متوقف شده بود و توسط Watchdog بسته شد؛ داده‌های ثبت‌شده حفظ شدند.",
                retryable=True,
                technical_details={
                    "reason": "stale_extraction_run",
                    "previous_status": previous_status,
                    "max_age_minutes": minutes,
                },
            )
        repaired_ids.append(str(run.id))
    return {"repaired_count": len(repaired_ids), "repaired_run_ids": repaired_ids}


def _mark_guard_failure(run_id: str, *, reason: str, exception_name: str = "") -> None:
    run = ExtractionRun.objects.filter(pk=run_id).prefetch_related("connectors").first()
    if run is None or run.status not in ACTIVE_STATUSES:
        return
    now = timezone.now()
    summary = dict(run.summary or {})
    summary["guard_failure"] = {
        "at": now.isoformat(),
        "reason": reason,
        "exception": exception_name,
        "captured_data_preserved": True,
    }
    run.status = ExtractionRun.Status.FAILED
    run.finished_at = now
    run.summary = summary
    run.save(update_fields=["status", "finished_at", "summary", "updated_at"])
    for connector in run.connectors.all():
        ExtractionError.objects.create(
            run=run,
            connector=connector,
            category=ExtractionError.Category.UNEXPECTED,
            safe_message="آزمون Connector پیش از پایان معتبر متوقف شد؛ داده‌های ثبت‌شده حفظ شدند.",
            retryable=True,
            technical_details={"reason": reason, "exception": exception_name},
        )


@shared_task(
    name="procurement.run_connector_acceptance",
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def run_connector_acceptance(run_id: str) -> dict:
    """Run exactly one connector with a bounded execution time."""
    try:
        result = run_extraction.run(run_id)
    except SoftTimeLimitExceeded:
        _mark_guard_failure(run_id, reason="soft_time_limit_exceeded", exception_name="SoftTimeLimitExceeded")
        return {"run_id": run_id, "status": "failed", "reason": "soft_time_limit_exceeded"}
    except Exception as exc:
        _mark_guard_failure(run_id, reason="unhandled_connector_exception", exception_name=exc.__class__.__name__)
        return {"run_id": run_id, "status": "failed", "reason": "unhandled_connector_exception"}

    run = ExtractionRun.objects.filter(pk=run_id).first()
    if run is not None:
        summary = dict(run.summary or {})
        acceptance = dict(summary.get("acceptance") or {})
        acceptance["task_completed_at"] = timezone.now().isoformat()
        acceptance["bounded_execution_seconds"] = 600
        summary["acceptance"] = acceptance
        run.summary = summary
        run.save(update_fields=["summary", "updated_at"])
    return result


@shared_task(name="procurement.reconcile_stale_extractions")
def reconcile_stale_extractions() -> dict:
    return repair_stale_extraction_runs(max_age_minutes=60)
