from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from .analysis_utils import notice_basis_hash, notice_basis_payload
from .models import ProcurementNotice
from .models_analysis import AnalysisBatch, AnalysisRequest, NoticeAnalysisDraft
from .models_extraction import ExtractionRunItem


MAX_ANALYSIS_ITEMS = 50
DEFAULT_ANALYSIS_ITEMS = 20


@dataclass(frozen=True)
class AnalysisWorkItem:
    notice: ProcurementNotice
    content_hash: str


def normalize_limit(value, *, default: int = DEFAULT_ANALYSIS_ITEMS) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, 1), MAX_ANALYSIS_ITEMS)


def _eligible_queryset(analysis_request: AnalysisRequest):
    queryset = (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        .exclude(processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
        .prefetch_related("source_links__source_notice")
        .order_by("-last_seen_at", "-created_at")
    )

    extraction_run = analysis_request.extraction_run
    if extraction_run_id := getattr(extraction_run, "id", None):
        source_notice_ids = list(
            ExtractionRunItem.objects.filter(
                run_id=extraction_run_id,
                status__in=[ExtractionRunItem.Status.NEW, ExtractionRunItem.Status.UPDATED],
                source_notice__isnull=False,
            ).values_list("source_notice_id", flat=True)
        )
        if source_notice_ids:
            queryset = queryset.filter(source_links__source_notice_id__in=source_notice_ids).distinct()
    return queryset


def collect_work_items(analysis_request: AnalysisRequest, *, limit: int) -> list[AnalysisWorkItem]:
    items: list[AnalysisWorkItem] = []
    for notice in _eligible_queryset(analysis_request)[:250]:
        basis_hash = notice_basis_hash(notice)
        already_analyzed = NoticeAnalysisDraft.objects.filter(
            notice=notice,
            context_snapshot=analysis_request.context_snapshot,
            notice_content_hash=basis_hash,
        ).exists()
        if already_analyzed:
            continue
        items.append(AnalysisWorkItem(notice=notice, content_hash=basis_hash))
        if len(items) >= limit:
            break
    return items


def _metadata_ids(analysis_request: AnalysisRequest) -> list[str]:
    values = (analysis_request.metadata or {}).get("candidate_notice_ids") or []
    return [str(value) for value in values if value]


def request_work_items(analysis_request: AnalysisRequest, *, limit: int | None = None) -> list[AnalysisWorkItem]:
    candidate_ids = _metadata_ids(analysis_request)
    if not candidate_ids:
        return []
    queryset = (
        ProcurementNotice.objects.filter(id__in=candidate_ids, soft_deleted_at__isnull=True, is_hidden=False)
        .prefetch_related("source_links__source_notice")
    )
    by_id = {str(notice.id): notice for notice in queryset}
    work: list[AnalysisWorkItem] = []
    for notice_id in candidate_ids:
        notice = by_id.get(notice_id)
        if notice is None:
            continue
        basis_hash = notice_basis_hash(notice)
        already_analyzed = NoticeAnalysisDraft.objects.filter(
            notice=notice,
            context_snapshot=analysis_request.context_snapshot,
            notice_content_hash=basis_hash,
        ).exists()
        if already_analyzed:
            continue
        work.append(AnalysisWorkItem(notice=notice, content_hash=basis_hash))
        if limit is not None and len(work) >= limit:
            break
    return work


@transaction.atomic
def start_analysis_request(analysis_request: AnalysisRequest, *, limit: int, actor: str) -> tuple[AnalysisRequest, AnalysisBatch | None]:
    locked = AnalysisRequest.objects.select_for_update().select_related("context_snapshot", "extraction_run").get(pk=analysis_request.pk)
    existing_batch = locked.batches.order_by("sequence").first()
    if existing_batch is not None and _metadata_ids(locked):
        return locked, existing_batch
    if locked.status not in {AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING}:
        raise ValueError("این درخواست تحلیل دیگر قابل شروع نیست.")

    work_items = collect_work_items(locked, limit=normalize_limit(limit))
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


def serialize_work(analysis_request: AnalysisRequest, *, limit: int) -> list[dict]:
    items = request_work_items(analysis_request, limit=normalize_limit(limit, default=10))
    return [
        {
            "notice_id": str(item.notice.id),
            "notice_content_hash": item.content_hash,
            "analysis_basis": notice_basis_payload(item.notice),
        }
        for item in items
    ]


@transaction.atomic
def finish_analysis_request(
    analysis_request: AnalysisRequest,
    *,
    actor: str,
    failed_notice_ids: Iterable[str] | None = None,
    summary: dict | None = None,
) -> tuple[AnalysisRequest, AnalysisBatch | None]:
    locked = AnalysisRequest.objects.select_for_update().select_related("context_snapshot").get(pk=analysis_request.pk)
    batch = locked.batches.order_by("-sequence").first()
    if batch is None:
        raise ValueError("برای این درخواست Batch فعالی وجود ندارد.")

    candidate_ids = _metadata_ids(locked)
    failed_ids = {str(value) for value in (failed_notice_ids or []) if str(value) in candidate_ids}
    completed_count = NoticeAnalysisDraft.objects.filter(batch=batch).count()
    unresolved_ids = set(candidate_ids) - set(
        str(value)
        for value in NoticeAnalysisDraft.objects.filter(batch=batch).values_list("notice_id", flat=True)
    )
    failed_ids |= unresolved_ids
    failed_count = len(failed_ids)
    now = timezone.now()

    if completed_count and failed_count:
        batch_status = AnalysisBatch.Status.PARTIAL
        request_status = AnalysisRequest.Status.COMPLETED
    elif failed_count:
        batch_status = AnalysisBatch.Status.FAILED
        request_status = AnalysisRequest.Status.FAILED
    elif completed_count:
        batch_status = AnalysisBatch.Status.COMPLETED
        request_status = AnalysisRequest.Status.COMPLETED
    else:
        batch_status = AnalysisBatch.Status.COMPLETED
        request_status = AnalysisRequest.Status.NO_CHANGES

    batch.status = batch_status
    batch.completed_count = completed_count
    batch.failed_count = failed_count
    batch.finished_at = now
    batch.summary = {
        **(batch.summary or {}),
        **(summary or {}),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "failed_notice_ids": sorted(failed_ids),
    }
    batch.save(update_fields=["status", "completed_count", "failed_count", "finished_at", "summary", "updated_at"])

    if failed_ids:
        ProcurementNotice.objects.filter(id__in=failed_ids).update(
            processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_FAILED
        )

    locked.status = request_status
    locked.completed_at = now
    locked.last_error = "" if request_status != AnalysisRequest.Status.FAILED else "تحلیل هیچ فراخوانی تکمیل نشد."
    locked.metadata = {
        **(locked.metadata or {}),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "failed_notice_ids": sorted(failed_ids),
    }
    locked.save(update_fields=["status", "completed_at", "last_error", "metadata", "updated_at"])
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_request.finish",
        target_type="analysis_request",
        target_id=str(locked.id),
        payload={
            "batch_id": str(batch.id),
            "status": request_status,
            "completed_count": completed_count,
            "failed_count": failed_count,
        },
    )
    return locked, batch
