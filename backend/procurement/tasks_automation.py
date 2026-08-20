from datetime import time

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from .automation_utils import calculate_next_extraction
from .models import ProcurementConnector
from .models_automation import ProcurementAutomationSettings
from .models_extraction import ExtractionRun, ExtractionRunItem
from .tasks import run_extraction

BOOTSTRAP_ACTION = "procurement.automation.bootstrap_guarded_v1"
ACTIVE_EXTRACTION_STATUSES = (
    ExtractionRun.Status.QUEUED,
    ExtractionRun.Status.RUNNING,
)
STALE_SCHEDULED_EXTRACTION_IDLE_SECONDS = 60 * 60


def bootstrap_guarded_automation() -> dict:
    if AuditEvent.objects.filter(action=BOOTSTRAP_ACTION).exists():
        return {"changed": False, "reason": "already_bootstrapped"}
    now = timezone.now()
    settings, _ = ProcurementAutomationSettings.objects.get_or_create(key="default")
    settings.enabled = True
    settings.cadence = ProcurementAutomationSettings.Cadence.HOURLY
    settings.interval_minutes = 60
    settings.daily_time = time(hour=7, minute=0)
    settings.timezone_name = "Asia/Tehran"
    settings.analysis_delay_minutes = 0
    settings.scheduled_task_enabled = True
    settings.next_extraction_at = calculate_next_extraction(settings, now=now)
    settings.last_schedule_sync_at = now
    settings.save()
    AuditEvent.objects.create(
        actor="system",
        action=BOOTSTRAP_ACTION,
        target_type="procurement_automation_settings",
        target_id=str(settings.id),
        payload={
            "enabled": True,
            "cadence": settings.cadence,
            "interval_minutes": settings.interval_minutes,
            "timezone_name": settings.timezone_name,
            "analysis_delay_minutes": settings.analysis_delay_minutes,
            "next_extraction_at": settings.next_extraction_at.isoformat() if settings.next_extraction_at else None,
            "draft_only": True,
        },
    )
    return {"changed": True, "settings_id": str(settings.id), "next_extraction_at": settings.next_extraction_at}


def _latest_persisted_extraction_activity(run: ExtractionRun):
    latest_page_at = (
        run.pages.exclude(captured_at__isnull=True)
        .order_by("-captured_at", "-created_at")
        .values_list("captured_at", flat=True)
        .first()
    )
    latest_item_at = run.items.order_by("-created_at").values_list("created_at", flat=True).first()
    latest_error_at = run.errors.order_by("-created_at").values_list("created_at", flat=True).first()
    candidates = [
        run.created_at,
        run.started_at,
        run.updated_at,
        latest_page_at,
        latest_item_at,
        latest_error_at,
    ]
    return max(value for value in candidates if value is not None)


def _recover_stale_scheduled_extractions(*, connector_ids: list, now) -> tuple[list[str], list[str]]:
    """Fail closed only orphaned scheduled incremental runs and preserve their evidence.

    This recovery is intentionally conservative. A run must be both eligible by
    trigger/mode and have no persisted page/item/error/run activity for one hour.
    Manual work is never auto-terminalized. Caller must hold a transaction because
    the active ExtractionRun rows are selected FOR UPDATE.
    """

    active_run_ids = (
        ExtractionRun.objects.filter(
            status__in=ACTIVE_EXTRACTION_STATUSES,
            connectors__in=connector_ids,
        )
        .values("pk")
        .distinct()
    )
    # Keep DISTINCT inside the ID subquery. PostgreSQL does not allow DISTINCT on
    # the outer SELECT FOR UPDATE query itself.
    active_runs = list(
        ExtractionRun.objects.select_for_update()
        .filter(pk__in=active_run_ids)
        .order_by("created_at")
    )
    recovered_ids: list[str] = []
    blocking_ids: list[str] = []

    for run in active_runs:
        latest_activity_at = _latest_persisted_extraction_activity(run)
        idle_seconds = max(0, int((now - latest_activity_at).total_seconds()))
        auto_recoverable = (
            run.trigger == ExtractionRun.Trigger.SCHEDULED
            and run.mode == ExtractionRun.Mode.INCREMENTAL
            and idle_seconds >= STALE_SCHEDULED_EXTRACTION_IDLE_SECONDS
        )
        if not auto_recoverable:
            blocking_ids.append(str(run.id))
            continue

        previous_status = run.status
        pages_recorded = run.pages.count()
        new_count = run.items.filter(status=ExtractionRunItem.Status.NEW).count()
        updated_count = run.items.filter(status=ExtractionRunItem.Status.UPDATED).count()
        duplicate_count = run.items.filter(status=ExtractionRunItem.Status.DUPLICATE).count()
        failed_count = run.items.filter(status=ExtractionRunItem.Status.FAILED).count()
        skipped_count = run.items.filter(status=ExtractionRunItem.Status.SKIPPED).count()
        items_recorded = new_count + updated_count + duplicate_count + failed_count + skipped_count
        errors_recorded = run.errors.count()
        connector_keys = list(run.connectors.values_list("key", flat=True))

        recovery = {
            "reason": "scheduled_incremental_idle_timeout",
            "previous_status": previous_status,
            "idle_seconds": idle_seconds,
            "idle_threshold_seconds": STALE_SCHEDULED_EXTRACTION_IDLE_SECONDS,
            "latest_activity_at": latest_activity_at.isoformat(),
            "recovered_at": now.isoformat(),
            "preserved_evidence": {
                "connector_keys": connector_keys,
                "pages_recorded": pages_recorded,
                "items_recorded": items_recorded,
                "errors_recorded": errors_recorded,
                "records_new": new_count,
                "records_updated": updated_count,
                "records_duplicate": duplicate_count,
                "records_failed": failed_count,
                "records_skipped": skipped_count,
            },
        }
        summary = dict(run.summary or {})
        summary["stale_recovery"] = recovery

        run.status = ExtractionRun.Status.FAILED
        run.finished_at = now
        run.pages_processed = pages_recorded
        run.records_seen = items_recorded
        run.records_new = new_count
        run.records_updated = updated_count
        run.records_duplicate = duplicate_count
        run.records_failed = failed_count
        run.summary = summary
        run.save(
            update_fields=[
                "status",
                "finished_at",
                "pages_processed",
                "records_seen",
                "records_new",
                "records_updated",
                "records_duplicate",
                "records_failed",
                "summary",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor="system",
            action="procurement.automation.stale_extraction_recovered",
            target_type="extraction_run",
            target_id=str(run.id),
            payload={
                **recovery,
                "terminal_status": ExtractionRun.Status.FAILED,
                "evidence_preserved": True,
                "records_deleted": 0,
            },
        )
        recovered_ids.append(str(run.id))

    return recovered_ids, blocking_ids


@shared_task(name="procurement.dispatch_due_extraction")
def dispatch_due_extraction() -> dict:
    settings_id = (
        ProcurementAutomationSettings.objects.filter(key="default")
        .values_list("id", flat=True)
        .first()
    )
    if settings_id is None:
        return {"dispatched": False, "reason": "automation_disabled"}

    with transaction.atomic():
        settings = ProcurementAutomationSettings.objects.select_for_update().get(pk=settings_id)
        if not settings.enabled:
            return {"dispatched": False, "reason": "automation_disabled"}

        now = timezone.now()
        if settings.next_extraction_at is None:
            settings.next_extraction_at = calculate_next_extraction(settings, now=now)
            settings.last_schedule_sync_at = now
            settings.save(update_fields=["next_extraction_at", "last_schedule_sync_at", "updated_at"])
            return {
                "dispatched": False,
                "reason": "schedule_initialized",
                "next_extraction_at": settings.next_extraction_at,
            }
        if settings.next_extraction_at > now:
            return {
                "dispatched": False,
                "reason": "not_due",
                "next_extraction_at": settings.next_extraction_at,
            }

        connectors = list(
            ProcurementConnector.objects.select_related("source").filter(
                enabled=True,
                source__enabled=True,
                status__in=[ProcurementConnector.Status.ACTIVE, ProcurementConnector.Status.ERROR],
            )
        )
        if not connectors:
            settings.next_extraction_at = calculate_next_extraction(settings, now=now)
            settings.last_schedule_sync_at = now
            settings.save(update_fields=["next_extraction_at", "last_schedule_sync_at", "updated_at"])
            return {"dispatched": False, "reason": "no_enabled_connectors"}

        connector_ids = [connector.id for connector in connectors]
        recovered_ids, blocking_ids = _recover_stale_scheduled_extractions(
            connector_ids=connector_ids,
            now=now,
        )
        if blocking_ids:
            return {
                "dispatched": False,
                "reason": "extraction_already_running",
                "blocking_run_ids": blocking_ids,
                "recovered_stale_run_ids": recovered_ids,
            }

        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            analyze_after_success=True,
        )
        run.connectors.set(connectors)
        settings.last_extraction_requested_at = now
        settings.last_schedule_sync_at = now
        settings.next_extraction_at = calculate_next_extraction(settings, now=now)
        settings.save(
            update_fields=[
                "last_extraction_requested_at",
                "last_schedule_sync_at",
                "next_extraction_at",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor="system",
            action="procurement.automation.extraction_dispatched",
            target_type="extraction_run",
            target_id=str(run.id),
            payload={
                "connector_keys": [c.key for c in connectors],
                "draft_only_analysis": True,
                "recovered_stale_run_ids": recovered_ids,
            },
        )
        transaction.on_commit(lambda run_id=str(run.id): run_extraction.delay(run_id))

    return {
        "dispatched": True,
        "run_id": str(run.id),
        "mode": run.mode,
        "connector_keys": [c.key for c in connectors],
        "next_extraction_at": settings.next_extraction_at,
        "recovered_stale_run_ids": recovered_ids,
    }


@shared_task(name="procurement.dispatch_due_analysis_requests")
def dispatch_due_analysis_requests() -> dict:
    """Compatibility task name retained for existing Celery Beat installations.

    The old implementation created at most twenty one-batch AnalysisRequest rows.
    The new implementation delegates to one persistent run that is resumed until
    its PostgreSQL queue is empty.
    """
    from .tasks_analysis_runs import dispatch_scheduled_analysis_run

    result = dispatch_scheduled_analysis_run()
    return {
        **result,
        "created": int(bool(result.get("dispatched"))),
        "persistent_run": True,
        "draft_only": True,
        "human_review_required": True,
    }
