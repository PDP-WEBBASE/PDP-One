from datetime import timedelta

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from .models import ProcurementConnector
from .models_extraction import ExtractionError, ExtractionRun
from .tasks import run_extraction

ACTIVE_STATUSES = (ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING)
AUTO_ACCEPTANCE_SUITE_ID = "release-v1-1-0-trial-acceptance-20260725"
AUTO_ACCEPTANCE_CONNECTORS = (
    "hezareh_tenders",
    "hezareh_inquiries",
    "parsnamad_inquiries",
    "setad_tenders",
    "setad_inquiries",
)
DISABLED_CONNECTOR_KEY = "parsnamad_tenders"


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


def ensure_release_connector_acceptance() -> dict:
    """Create the release acceptance suite once; subsequent calls are read-only."""
    existing = list(
        ExtractionRun.objects.filter(summary__acceptance__suite_id=AUTO_ACCEPTANCE_SUITE_ID)
        .prefetch_related("connectors")
        .order_by("created_at")
    )
    if existing:
        return {
            "started": False,
            "reason": "suite_already_exists",
            "suite_id": AUTO_ACCEPTANCE_SUITE_ID,
            "runs": [
                {
                    "run_id": str(run.id),
                    "status": run.status,
                    "connector_keys": list(run.connectors.values_list("key", flat=True)),
                }
                for run in existing
            ],
        }

    stale_result = repair_stale_extraction_runs(max_age_minutes=30)
    disabled = ProcurementConnector.objects.filter(key=DISABLED_CONNECTOR_KEY).first()
    disabled_changed = False
    if disabled is not None and (disabled.enabled or disabled.status != ProcurementConnector.Status.INACTIVE):
        disabled.enabled = False
        disabled.status = ProcurementConnector.Status.INACTIVE
        disabled.save(update_fields=["enabled", "status", "updated_at"])
        disabled_changed = True

    now = timezone.now()
    created: list[dict] = []
    skipped: list[dict] = []
    with transaction.atomic():
        for key in AUTO_ACCEPTANCE_CONNECTORS:
            connector = ProcurementConnector.objects.select_related("source").filter(key=key).first()
            if connector is None:
                skipped.append({"connector_key": key, "reason": "connector_not_found"})
                continue
            if not connector.enabled or not connector.source.enabled:
                skipped.append({"connector_key": key, "reason": "connector_disabled"})
                continue
            run = ExtractionRun.objects.create(
                trigger=ExtractionRun.Trigger.MANUAL,
                mode=ExtractionRun.Mode.MANUAL_RANGE,
                lookback_days=7,
                status=ExtractionRun.Status.QUEUED,
                requested_by=None,
                include_details=False,
                analyze_after_success=False,
                page_cap=3,
                summary={
                    "acceptance": {
                        "suite_id": AUTO_ACCEPTANCE_SUITE_ID,
                        "connector_key": key,
                        "requested_at": now.isoformat(),
                        "page_cap": 3,
                        "lookback_days": 7,
                        "real_source_data": True,
                        "include_details": False,
                        "automatic_release_acceptance": True,
                    }
                },
            )
            run.connectors.set([connector])
            created.append({"connector_key": key, "run_id": str(run.id)})

        AuditEvent.objects.create(
            actor="system",
            action="procurement.connector_acceptance.auto_start",
            target_type="connector_acceptance_suite",
            target_id=AUTO_ACCEPTANCE_SUITE_ID,
            payload={
                "runs": created,
                "skipped": skipped,
                "stale_repair": stale_result,
                "parsnamad_tenders_disabled": True,
                "parsnamad_tenders_changed": disabled_changed,
            },
        )

    for item in created:
        run_connector_acceptance.delay(item["run_id"])

    return {
        "started": True,
        "suite_id": AUTO_ACCEPTANCE_SUITE_ID,
        "runs": created,
        "skipped": skipped,
        "stale_repair": stale_result,
        "parsnamad_tenders_disabled": True,
    }


@shared_task(name="procurement.reconcile_stale_extractions")
def reconcile_stale_extractions() -> dict:
    return repair_stale_extraction_runs(max_age_minutes=60)


@shared_task(name="procurement.ensure_release_connector_acceptance")
def ensure_release_connector_acceptance_task() -> dict:
    return ensure_release_connector_acceptance()
