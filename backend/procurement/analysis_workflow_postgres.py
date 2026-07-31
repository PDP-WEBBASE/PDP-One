from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from . import analysis_workflow as base
from .models import ProcurementNotice
from .models_analysis import AnalysisBatch, AnalysisRequest


@transaction.atomic
def start_analysis_request(analysis_request: AnalysisRequest, *, limit: int, actor: str):
    # Both context_snapshot and extraction_run are nullable foreign keys.
    # PostgreSQL rejects FOR UPDATE when either nullable relation is joined.
    # Lock only the AnalysisRequest row; related objects are loaded lazily.
    locked = AnalysisRequest.objects.select_for_update().get(pk=analysis_request.pk)
    existing_batch = locked.batches.order_by("sequence").first()
    if existing_batch is not None and base._metadata_ids(locked):
        return locked, existing_batch
    if locked.status not in {AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING}:
        raise ValueError("این درخواست تحلیل دیگر قابل شروع نیست.")

    work_items = base.collect_work_items(locked, limit=base.normalize_limit(limit))
    now = timezone.now()
    if not work_items:
        locked.status = AnalysisRequest.Status.NO_CHANGES
        locked.started_at = locked.started_at or now
        locked.completed_at = now
        locked.metadata = {
            **(locked.metadata or {}),
            "candidate_notice_ids": [],
            "candidate_count": 0,
            "context_version": locked.context_snapshot.version,
            "result": "no_changes",
        }
        locked.save(update_fields=["status", "started_at", "completed_at", "metadata", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_request.no_changes",
            target_type="analysis_request",
            target_id=str(locked.id),
            payload={"context_version": locked.context_snapshot.version},
        )
        return locked, None

    candidate_ids = [str(item.notice.id) for item in work_items]
    batch = AnalysisBatch.objects.create(
        request=locked,
        context_snapshot=locked.context_snapshot,
        status=AnalysisBatch.Status.PROCESSING,
        sequence=locked.batches.count() + 1,
        item_count=len(work_items),
        started_at=now,
        summary={"candidate_notice_ids": candidate_ids},
    )
    locked.status = AnalysisRequest.Status.PROCESSING
    locked.started_at = locked.started_at or now
    locked.metadata = {
        **(locked.metadata or {}),
        "candidate_notice_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "batch_id": str(batch.id),
        "context_version": locked.context_snapshot.version,
    }
    locked.save(update_fields=["status", "started_at", "metadata", "updated_at"])
    ProcurementNotice.objects.filter(id__in=candidate_ids).exclude(
        processing_status=ProcurementNotice.ProcessingStatus.ANALYZED
    ).update(processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_QUEUED)
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_request.start",
        target_type="analysis_request",
        target_id=str(locked.id),
        payload={
            "batch_id": str(batch.id),
            "candidate_count": len(candidate_ids),
            "context_version": locked.context_snapshot.version,
            "extraction_run": str(locked.extraction_run_id or ""),
        },
    )
    return locked, batch
