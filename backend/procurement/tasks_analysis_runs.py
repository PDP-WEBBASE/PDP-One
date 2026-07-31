from celery import shared_task
from django.utils import timezone

from core.models import AuditEvent

from .analysis_run_service import (
    active_run,
    create_dataset,
    create_or_resume_run,
    export_dataset,
    finalize_run_if_exhausted,
    initialize_run,
    refresh_run_counters,
)
from .models_analysis_runs import ProcurementAnalysisDataset, ProcurementAnalysisRun
from .models_automation import ProcurementAutomationSettings


@shared_task(name="procurement.initialize_analysis_run")
def initialize_analysis_run_task(run_id: str) -> dict:
    run = initialize_run(run_id, actor="celery-worker")
    return {"run_id": str(run.id), "status": run.status, "counters": run.counters}


@shared_task(name="procurement.export_analysis_dataset")
def export_analysis_dataset_task(dataset_id: str) -> dict:
    dataset = export_dataset(dataset_id, actor="celery-worker")
    return {
        "dataset_id": str(dataset.id),
        "run_id": str(dataset.run_id),
        "status": dataset.status,
        "record_count": dataset.record_count,
        "shard_count": dataset.shard_count,
    }


@shared_task(name="procurement.continue_analysis_run")
def continue_analysis_run_task(run_id: str) -> dict:
    run = ProcurementAnalysisRun.objects.get(pk=run_id)
    counters = refresh_run_counters(run)
    if counters["remaining"] == 0:
        run = finalize_run_if_exhausted(run, actor="celery-worker")
    elif run.status not in {
        ProcurementAnalysisRun.Status.PAUSED,
        ProcurementAnalysisRun.Status.CANCELLING,
        ProcurementAnalysisRun.Status.CANCELLED,
    }:
        run.status = ProcurementAnalysisRun.Status.RUNNING
        run.heartbeat_at = timezone.now()
        run.save(update_fields=["status", "heartbeat_at", "updated_at"])
    return {"run_id": str(run.id), "status": run.status, "counters": run.counters}


@shared_task(name="procurement.dispatch_scheduled_analysis_run")
def dispatch_scheduled_analysis_run() -> dict:
    settings = ProcurementAutomationSettings.objects.filter(
        key="default",
        enabled=True,
        scheduled_task_enabled=True,
    ).first()
    if settings is None:
        return {"dispatched": False, "reason": "automation_disabled"}

    current = active_run()
    if current:
        continue_analysis_run_task.delay(str(current.id))
        return {
            "dispatched": False,
            "continued": True,
            "run_id": str(current.id),
            "status": current.status,
        }

    try:
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.SCHEDULED,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor="scheduled-task",
            shard_size=250,
            deep_analysis_batch_size=25,
            parallel_workers=4,
            max_retries_per_record=2,
        )
    except ValueError as exc:
        return {"dispatched": False, "reason": str(exc)}

    if created:
        initialize_analysis_run_task.delay(str(run.id))
        AuditEvent.objects.create(
            actor="scheduled-task",
            action="procurement.analysis_run.scheduled_dispatch",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={"run_type": run.run_type, "scope": run.scope, "draft_only": True},
        )
    return {"dispatched": created, "continued": not created, "run_id": str(run.id), "status": run.status}


@shared_task(name="procurement.ensure_analysis_dataset")
def ensure_analysis_dataset_task(run_id: str) -> dict:
    run = ProcurementAnalysisRun.objects.select_related("context_snapshot").get(pk=run_id)
    dataset = run.datasets.filter(status__in=[
        ProcurementAnalysisDataset.Status.PENDING,
        ProcurementAnalysisDataset.Status.PREPARING,
        ProcurementAnalysisDataset.Status.READY,
    ]).order_by("-created_at").first()
    if dataset is None:
        dataset = create_dataset(run)
        export_analysis_dataset_task.delay(str(dataset.id))
    return {"dataset_id": str(dataset.id), "status": dataset.status}
