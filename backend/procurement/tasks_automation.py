from datetime import time, timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from .automation_utils import calculate_next_extraction
from .models import ProcurementConnector
from .models_analysis import AnalysisContextSnapshot, AnalysisRequest
from .models_automation import ProcurementAutomationSettings
from .models_extraction import ExtractionRun
from .tasks import run_extraction

BOOTSTRAP_ACTION = "procurement.automation.bootstrap_guarded_v1"


def bootstrap_guarded_automation() -> dict:
    if AuditEvent.objects.filter(action=BOOTSTRAP_ACTION).exists():
        return {"changed": False, "reason": "already_bootstrapped"}
    now = timezone.now()
    settings, _ = ProcurementAutomationSettings.objects.get_or_create(key="default")
    settings.enabled = True
    settings.cadence = ProcurementAutomationSettings.Cadence.DAILY
    settings.daily_time = time(hour=7, minute=0)
    settings.timezone_name = "Asia/Tehran"
    settings.analysis_delay_minutes = 15
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
            "daily_time": str(settings.daily_time),
            "timezone_name": settings.timezone_name,
            "analysis_delay_minutes": settings.analysis_delay_minutes,
            "next_extraction_at": settings.next_extraction_at.isoformat() if settings.next_extraction_at else None,
            "draft_only": True,
        },
    )
    return {"changed": True, "settings_id": str(settings.id), "next_extraction_at": settings.next_extraction_at}


@shared_task(name="procurement.dispatch_due_extraction")
def dispatch_due_extraction() -> dict:
    settings = ProcurementAutomationSettings.objects.filter(key="default").first()
    if settings is None or not settings.enabled:
        return {"dispatched": False, "reason": "automation_disabled"}

    now = timezone.now()
    if settings.next_extraction_at is None:
        settings.next_extraction_at = calculate_next_extraction(settings, now=now)
        settings.last_schedule_sync_at = now
        settings.save(update_fields=["next_extraction_at", "last_schedule_sync_at", "updated_at"])
        return {"dispatched": False, "reason": "schedule_initialized", "next_extraction_at": settings.next_extraction_at}
    if settings.next_extraction_at > now:
        return {"dispatched": False, "reason": "not_due", "next_extraction_at": settings.next_extraction_at}

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
    conflict = ExtractionRun.objects.filter(
        status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING],
        connectors__in=connector_ids,
    ).exists()
    if conflict:
        return {"dispatched": False, "reason": "extraction_already_running"}

    with transaction.atomic():
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
        settings.save(update_fields=["last_extraction_requested_at", "last_schedule_sync_at", "next_extraction_at", "updated_at"])
        AuditEvent.objects.create(
            actor="system",
            action="procurement.automation.extraction_dispatched",
            target_type="extraction_run",
            target_id=str(run.id),
            payload={"connector_keys": [c.key for c in connectors], "draft_only_analysis": True},
        )
        transaction.on_commit(lambda: run_extraction.delay(str(run.id)))

    return {"dispatched": True, "run_id": str(run.id), "mode": run.mode, "connector_keys": [c.key for c in connectors], "next_extraction_at": settings.next_extraction_at}


@shared_task(name="procurement.dispatch_due_analysis_requests")
def dispatch_due_analysis_requests() -> dict:
    settings = ProcurementAutomationSettings.objects.filter(key="default", enabled=True).first()
    if settings is None:
        return {"created": 0, "reason": "automation_disabled"}
    context = AnalysisContextSnapshot.objects.filter(status=AnalysisContextSnapshot.Status.ACTIVE).order_by("-version").first()
    if context is None:
        return {"created": 0, "reason": "no_active_analysis_context"}

    eligible_statuses = [ExtractionRun.Status.SUCCEEDED, ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS, ExtractionRun.Status.PARTIAL]
    runs = ExtractionRun.objects.filter(
        trigger=ExtractionRun.Trigger.SCHEDULED,
        analyze_after_success=True,
        status__in=eligible_statuses,
        analysis_requests__isnull=True,
    ).order_by("created_at")[:20]
    created_ids = []
    for run in runs:
        changed = int(run.records_new or 0) + int(run.records_updated or 0)
        if changed <= 0:
            AnalysisRequest.objects.create(
                trigger=AnalysisRequest.Trigger.SCHEDULED,
                command="PDP",
                status=AnalysisRequest.Status.NO_CHANGES,
                extraction_run=run,
                context_snapshot=context,
                completed_at=timezone.now(),
                metadata={"reason": "no_new_or_changed_records", "draft_only": True},
            )
            continue
        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.SCHEDULED,
            command="PDP",
            status=AnalysisRequest.Status.PENDING,
            extraction_run=run,
            context_snapshot=context,
            eligible_after=timezone.now() + timedelta(minutes=max(0, settings.analysis_delay_minutes)),
            metadata={
                "records_new": run.records_new,
                "records_updated": run.records_updated,
                "records_failed": run.records_failed,
                "draft_only": True,
                "human_review_required": True,
            },
        )
        created_ids.append(str(request_record.id))
        AuditEvent.objects.create(
            actor="system",
            action="procurement.automation.analysis_request_queued",
            target_type="analysis_request",
            target_id=str(request_record.id),
            payload={"extraction_run_id": str(run.id), "draft_only": True, "human_review_required": True},
        )
    return {"created": len(created_ids), "request_ids": created_ids, "draft_only": True, "human_review_required": True}
