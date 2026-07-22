from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .automation_utils import calculate_next_extraction
from .models import ProcurementConnector
from .models_automation import ProcurementAutomationSettings
from .models_extraction import ExtractionRun
from .tasks import run_extraction


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
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            analyze_after_success=False,
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
        transaction.on_commit(lambda: run_extraction.delay(str(run.id)))

    return {
        "dispatched": True,
        "run_id": str(run.id),
        "connector_keys": [connector.key for connector in connectors],
        "next_extraction_at": settings.next_extraction_at,
    }
