from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.models import AuditEvent

from .analysis_utils import get_active_context, notice_basis_hash, notice_basis_payload
from .models import ProcurementNotice
from .models_analysis import AnalysisBatch, AnalysisRequest, NoticeAnalysisDraft
from .models_analysis_runs import (
    ProcurementAnalysisDataset,
    ProcurementAnalysisImport,
    ProcurementAnalysisRun,
    ProcurementAnalysisRunItem,
)

TERMINAL_ITEM_STATUSES = {
    ProcurementAnalysisRunItem.Status.COMPLETED,
    ProcurementAnalysisRunItem.Status.POISON,
    ProcurementAnalysisRunItem.Status.FAILED,
    ProcurementAnalysisRunItem.Status.CANCELLED,
    ProcurementAnalysisRunItem.Status.SKIPPED,
}
OPEN_ITEM_STATUSES = {
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
    ProcurementAnalysisRunItem.Status.RETRY,
}


def _deadline_priority(notice: ProcurementNotice) -> str:
    if not notice.submission_deadline:
        return "unknown"
    remaining = notice.submission_deadline - timezone.now()
    if remaining.total_seconds() < 0:
        return "expired"
    if remaining <= timedelta(hours=24):
        return "urgent"
    if remaining <= timedelta(days=3):
        return "high"
    if remaining <= timedelta(days=7):
        return "medium"
    return "normal"


def _candidate_queryset(run: ProcurementAnalysisRun):
    queryset = (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        .exclude(processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
        .prefetch_related("source_links__source_notice__connector__source")
        .order_by("created_at", "id")
    )
    if not run.include_expired:
        queryset = queryset.filter(Q(submission_deadline__isnull=True) | Q(submission_deadline__gte=timezone.now()))
    if run.scope == ProcurementAnalysisRun.Scope.RETRY_FAILED:
        queryset = queryset.filter(processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_FAILED)
    elif run.scope == ProcurementAnalysisRun.Scope.MANUAL_SELECTION:
        queryset = queryset.filter(id__in=[str(value) for value in run.manual_notice_ids])
    elif run.scope == ProcurementAnalysisRun.Scope.NEW:
        queryset = queryset.filter(analysis_drafts__isnull=True)
    elif run.scope == ProcurementAnalysisRun.Scope.CHANGED:
        queryset = queryset.filter(analysis_drafts__isnull=False).distinct()
    return queryset


def _analysis_reason(run: ProcurementAnalysisRun, notice: ProcurementNotice, basis_hash: str) -> str | None:
    drafts = list(notice.analysis_drafts.all()) if hasattr(notice, "analysis_drafts") else []
    current = [draft for draft in drafts if draft.context_snapshot_id == run.context_snapshot_id]
    exact = [draft for draft in current if draft.notice_content_hash == basis_hash]

    if run.include_previously_analyzed:
        return "explicit_reanalysis"
    if notice.processing_status == ProcurementNotice.ProcessingStatus.ANALYSIS_FAILED:
        return "previous_analysis_failed"
    if exact:
        for draft in exact:
            review = (draft.raw_output or {}).get("human_review") or {}
            if review.get("decision") == "needs_revision":
                return "returned_for_completion"
        return None
    if not drafts:
        return "never_analyzed"
    if not current:
        return "analysis_context_changed"
    return "notice_content_changed"


def _ensure_legacy_batch(run: ProcurementAnalysisRun) -> AnalysisBatch:
    if run.analysis_request_id:
        batch = run.analysis_request.batches.order_by("sequence").first()
        if batch:
            return batch
    request_record = AnalysisRequest.objects.create(
        trigger=(
            AnalysisRequest.Trigger.SCHEDULED
            if run.trigger == ProcurementAnalysisRun.Trigger.SCHEDULED
            else AnalysisRequest.Trigger.MANUAL_CHATGPT
            if run.trigger == ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT
            else AnalysisRequest.Trigger.MANUAL_WEB
        ),
        command="PDP",
        status=AnalysisRequest.Status.PROCESSING,
        extraction_run=run.extraction_run,
        context_snapshot=run.context_snapshot,
        requested_by=run.requested_by,
        started_at=run.started_at or timezone.now(),
        metadata={
            "persistent_run_id": str(run.id),
            "run_type": run.run_type,
            "scope": run.scope,
            "draft_only": True,
            "human_review_required": True,
        },
    )
    batch = AnalysisBatch.objects.create(
        request=request_record,
        context_snapshot=run.context_snapshot,
        status=AnalysisBatch.Status.PROCESSING,
        sequence=1,
        item_count=0,
        started_at=run.started_at or timezone.now(),
        summary={"persistent_run_id": str(run.id)},
    )
    run.analysis_request = request_record
    run.save(update_fields=["analysis_request", "updated_at"])
    return batch


def active_run():
    return ProcurementAnalysisRun.objects.select_related("context_snapshot", "requested_by").filter(
        status__in=ProcurementAnalysisRun.ACTIVE_STATUSES
    ).order_by("created_at").first()


@transaction.atomic
def create_or_resume_run(
    *,
    run_type: str,
    trigger: str,
    scope: str,
    actor: str,
    requested_by=None,
    include_expired: bool = False,
    include_previously_analyzed: bool = False,
    manual_notice_ids: list[str] | None = None,
    shard_size: int = 250,
    deep_analysis_batch_size: int = 25,
    parallel_workers: int = 4,
    max_retries_per_record: int = 2,
    extraction_run=None,
) -> tuple[ProcurementAnalysisRun, bool]:
    existing = active_run()
    if existing:
        return existing, False
    context = get_active_context()
    if context is None:
        raise ValueError("هیچ Context فعال تحلیل تعریف نشده است.")
    try:
        run = ProcurementAnalysisRun.objects.create(
            run_type=run_type,
            trigger=trigger,
            scope=scope,
            status=ProcurementAnalysisRun.Status.PENDING,
            context_snapshot=context,
            extraction_run=extraction_run,
            requested_by=requested_by,
            include_expired=include_expired,
            include_previously_analyzed=include_previously_analyzed,
            manual_notice_ids=manual_notice_ids or [],
            export_shard_size=max(1, min(int(shard_size), 5000)),
            deep_analysis_batch_size=max(1, min(int(deep_analysis_batch_size), 250)),
            parallel_workers=max(1, min(int(parallel_workers), 16)),
            max_retries_per_record=max(0, min(int(max_retries_per_record), 10)),
            metadata={"draft_only": True, "human_review_required": True},
        )
    except IntegrityError:
        existing = active_run()
        if existing:
            return existing, False
        raise
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_run.create",
        target_type="procurement_analysis_run",
        target_id=str(run.id),
        payload={
            "run_type": run.run_type,
            "trigger": run.trigger,
            "scope": run.scope,
            "context_id": str(context.id),
            "context_hash": context.content_hash,
            "draft_only": True,
        },
    )
    return run, True


@transaction.atomic
def initialize_run(run_id: str, *, actor: str = "system") -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().select_related("context_snapshot").get(pk=run_id)
    if run.status not in {ProcurementAnalysisRun.Status.PENDING, ProcurementAnalysisRun.Status.PREPARING}:
        return run
    run.status = ProcurementAnalysisRun.Status.PREPARING
    run.started_at = run.started_at or timezone.now()
    run.heartbeat_at = timezone.now()
    run.save(update_fields=["status", "started_at", "heartbeat_at", "updated_at"])
    batch = _ensure_legacy_batch(run)

    existing_ids = set(run.items.values_list("notice_id", flat=True))
    sequence = run.items.count()
    buffer: list[ProcurementAnalysisRunItem] = []
    counts = {"scanned": 0, "eligible": 0, "already_valid": 0}
    for notice in _candidate_queryset(run).iterator(chunk_size=500):
        counts["scanned"] += 1
        if notice.id in existing_ids:
            continue
        basis_hash = notice_basis_hash(notice)
        reason = _analysis_reason(run, notice, basis_hash)
        if reason is None:
            counts["already_valid"] += 1
            continue
        sequence += 1
        counts["eligible"] += 1
        buffer.append(
            ProcurementAnalysisRunItem(
                run=run,
                notice=notice,
                notice_content_hash=basis_hash,
                context_hash=run.context_snapshot.content_hash,
                analysis_reason=reason,
                deadline_priority=_deadline_priority(notice),
                shard_number=((sequence - 1) // run.export_shard_size) + 1,
                sequence=sequence,
            )
        )
        if len(buffer) >= 500:
            ProcurementAnalysisRunItem.objects.bulk_create(buffer, ignore_conflicts=True)
            buffer.clear()
    if buffer:
        ProcurementAnalysisRunItem.objects.bulk_create(buffer, ignore_conflicts=True)

    total = run.items.count()
    batch.item_count = total
    batch.save(update_fields=["item_count", "updated_at"])
    run.counters = {**counts, "total": total, "remaining": total, "completed": 0, "failed": 0}
    run.last_checkpoint = {"sequence": 0, "shard": 0, "initialized_at": timezone.now().isoformat()}
    if total:
        run.status = ProcurementAnalysisRun.Status.RUNNING
    else:
        run.status = ProcurementAnalysisRun.Status.NO_CHANGES
        run.finished_at = timezone.now()
        run.analysis_request.status = AnalysisRequest.Status.NO_CHANGES
        run.analysis_request.completed_at = run.finished_at
        run.analysis_request.save(update_fields=["status", "completed_at", "updated_at"])
        batch.status = AnalysisBatch.Status.COMPLETED
        batch.finished_at = run.finished_at
        batch.save(update_fields=["status", "finished_at", "updated_at"])
    run.heartbeat_at = timezone.now()
    run.save(update_fields=["status", "counters", "last_checkpoint", "finished_at", "heartbeat_at", "updated_at"])
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_run.initialized",
        target_type="procurement_analysis_run",
        target_id=str(run.id),
        payload={**counts, "total": total, "context_hash": run.context_snapshot.content_hash},
    )
    return run


def refresh_run_counters(run: ProcurementAnalysisRun, *, save: bool = True) -> dict[str, int]:
    aggregate = run.items.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.PENDING)),
        claimed=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.CLAIMED)),
        screened=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.SCREENED)),
        waiting_deep_analysis=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS)),
        completed=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.COMPLETED)),
        retry=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.RETRY)),
        poison=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.POISON)),
        failed=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.FAILED)),
        cancelled=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.CANCELLED)),
        skipped=Count("id", filter=Q(status=ProcurementAnalysisRunItem.Status.SKIPPED)),
    )
    counters = {key: int(value or 0) for key, value in aggregate.items()}
    counters["remaining"] = sum(counters.get(status, 0) for status in [
        "pending", "claimed", "screened", "waiting_deep_analysis", "retry"
    ])
    if save:
        run.counters = {**(run.counters or {}), **counters}
        run.heartbeat_at = timezone.now()
        run.save(update_fields=["counters", "heartbeat_at", "updated_at"])
    return counters


@transaction.atomic
def claim_run_items(run_id: str, *, worker_id: str, limit: int = 25, lease_seconds: int = 900) -> list[ProcurementAnalysisRunItem]:
    run = ProcurementAnalysisRun.objects.select_for_update().select_related("context_snapshot").get(pk=run_id)
    if run.status == ProcurementAnalysisRun.Status.PAUSED:
        return []
    if run.status in {ProcurementAnalysisRun.Status.CANCELLING, ProcurementAnalysisRun.Status.CANCELLED}:
        return []
    if run.status not in {ProcurementAnalysisRun.Status.RUNNING, ProcurementAnalysisRun.Status.WAITING_FOR_RESULTS}:
        raise ValueError("Run در وضعیت قابل Claim نیست.")
    now = timezone.now()
    run.items.filter(
        status=ProcurementAnalysisRunItem.Status.CLAIMED,
        claim_expires_at__lt=now,
    ).update(
        status=ProcurementAnalysisRunItem.Status.RETRY,
        claim_token=None,
        claimed_by="",
        claimed_at=None,
        claim_expires_at=None,
        last_error="claim_lease_expired",
    )
    queryset = run.items.filter(
        status__in=[ProcurementAnalysisRunItem.Status.PENDING, ProcurementAnalysisRunItem.Status.RETRY]
    ).order_by("sequence")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    selected = list(queryset[: max(1, min(int(limit), 250))])
    expires = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))
    for item in selected:
        item.new_claim_token()
        item.status = ProcurementAnalysisRunItem.Status.CLAIMED
        item.claimed_by = worker_id[:120]
        item.claimed_at = now
        item.claim_expires_at = expires
        item.attempts += 1
        item.save(update_fields=[
            "claim_token", "status", "claimed_by", "claimed_at", "claim_expires_at", "attempts", "updated_at"
        ])
    if selected:
        run.status = ProcurementAnalysisRun.Status.WAITING_FOR_RESULTS
        run.heartbeat_at = now
        run.save(update_fields=["status", "heartbeat_at", "updated_at"])
    return selected


def serialize_claimed_items(items: Iterable[ProcurementAnalysisRunItem]) -> list[dict[str, Any]]:
    payload = []
    for item in items:
        notice = item.notice
        payload.append({
            "run_item_id": str(item.id),
            "claim_token": str(item.claim_token),
            "notice_id": str(notice.id),
            "notice_content_hash": item.notice_content_hash,
            "context_id": str(item.run.context_snapshot_id),
            "context_version": item.run.context_snapshot.version,
            "context_hash": item.context_hash,
            "analysis_reason": item.analysis_reason,
            "deadline_priority": item.deadline_priority,
            "analysis_basis": notice_basis_payload(notice),
        })
    return payload


def _draft_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_recommended": bool(result.get("is_recommended", False)),
        "score": max(0, min(int(result.get("score", 0)), 100)),
        "priority": str(result.get("priority", "medium")),
        "fit_for_pdp": str(result.get("fit_for_pdp", ""))[:5000],
        "category": str(result.get("category", ""))[:200],
        "reason": str(result.get("reason", ""))[:10000],
        "recommended_action": str(result.get("recommended_action", ""))[:5000],
        "matched_experience": list(result.get("matched_experience") or []),
        "risk_notes": list(result.get("risk_notes") or []),
        "confidence": max(0, min(float(result.get("confidence", 0)), 100)),
    }


def import_result_records(
    *,
    run_id: str,
    results: list[dict[str, Any]],
    actor: str,
    dataset_id: str | None = None,
    result_hash: str = "",
    dry_run: bool = False,
) -> ProcurementAnalysisImport:
    run = ProcurementAnalysisRun.objects.select_for_update().select_related("context_snapshot").get(pk=run_id)
    dataset = None
    if dataset_id:
        dataset = ProcurementAnalysisDataset.objects.get(pk=dataset_id, run=run)
    import_record = ProcurementAnalysisImport.objects.create(
        run=run,
        dataset=dataset,
        status=ProcurementAnalysisImport.Status.VALIDATING,
        result_hash=result_hash[:64],
        dry_run=dry_run,
        started_at=timezone.now(),
    )
    batch = _ensure_legacy_batch(run)
    counts = {
        "total": len(results),
        "imported": 0,
        "duplicate": 0,
        "rejected": 0,
        "invalid_hash": 0,
        "invalid_context": 0,
        "error": 0,
    }
    errors: list[dict[str, str]] = []
    import_record.status = ProcurementAnalysisImport.Status.IMPORTING
    import_record.save(update_fields=["status", "updated_at"])

    for index, result in enumerate(results, start=1):
        try:
            item = run.items.select_related("notice").get(pk=result.get("run_item_id"))
            if str(result.get("claim_token", "")) != str(item.claim_token or ""):
                counts["rejected"] += 1
                errors.append({"index": str(index), "error": "claim_token_mismatch"})
                continue
            if str(result.get("notice_id", "")) != str(item.notice_id):
                counts["rejected"] += 1
                errors.append({"index": str(index), "error": "notice_id_mismatch"})
                continue
            if str(result.get("notice_content_hash", "")) != item.notice_content_hash:
                counts["invalid_hash"] += 1
                errors.append({"index": str(index), "error": "notice_content_hash_mismatch"})
                continue
            if str(result.get("context_hash", "")) != run.context_snapshot.content_hash:
                counts["invalid_context"] += 1
                errors.append({"index": str(index), "error": "context_hash_mismatch"})
                continue
            current_hash = notice_basis_hash(item.notice)
            if current_hash != item.notice_content_hash:
                counts["invalid_hash"] += 1
                item.status = ProcurementAnalysisRunItem.Status.RETRY
                item.last_error = "notice_changed_after_claim"
                item.claim_token = None
                item.save(update_fields=["status", "last_error", "claim_token", "updated_at"])
                continue

            existing = NoticeAnalysisDraft.objects.filter(
                notice=item.notice,
                context_snapshot=run.context_snapshot,
                notice_content_hash=item.notice_content_hash,
            ).first()
            if existing:
                counts["duplicate"] += 1
                if not dry_run:
                    item.draft = existing
                    item.status = ProcurementAnalysisRunItem.Status.COMPLETED
                    item.completed_at = timezone.now()
                    item.save(update_fields=["draft", "status", "completed_at", "updated_at"])
                continue
            if dry_run:
                counts["imported"] += 1
                continue

            fields = _draft_payload(result)
            raw_output = {
                "engine": "PDP One persistent analysis run",
                "decision_is_draft": True,
                "requires_human_review": True,
                "run_id": str(run.id),
                "run_item_id": str(item.id),
                "claim_token": str(item.claim_token),
                "context_hash": run.context_snapshot.content_hash,
                "screening_reason": result.get("screening_reason", ""),
                "urgency": result.get("urgency", ""),
                "analysis_mode": result.get("analysis_mode", "deep"),
                "matched_qualifications": result.get("matched_qualifications") or [],
                "missing_information": result.get("missing_information") or [],
                "result_metadata": result.get("result_metadata") or {},
            }
            draft = NoticeAnalysisDraft.objects.create(
                notice=item.notice,
                batch=batch,
                context_snapshot=run.context_snapshot,
                notice_content_hash=item.notice_content_hash,
                raw_output=raw_output,
                model_label=str(result.get("model_label") or "ChatGPT")[:100],
                review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
                created_by_label="ChatGPT",
                **fields,
            )
            item.draft = draft
            item.status = ProcurementAnalysisRunItem.Status.COMPLETED
            item.result_metadata = raw_output
            item.completed_at = timezone.now()
            item.claim_token = None
            item.claim_expires_at = None
            item.save(update_fields=[
                "draft", "status", "result_metadata", "completed_at", "claim_token", "claim_expires_at", "updated_at"
            ])
            item.notice.processing_status = ProcurementNotice.ProcessingStatus.ANALYZED
            item.notice.save(update_fields=["processing_status", "updated_at"])
            counts["imported"] += 1
        except (ProcurementAnalysisRunItem.DoesNotExist, ValueError, TypeError, IntegrityError) as exc:
            counts["error"] += 1
            errors.append({"index": str(index), "error": str(exc)[:300]})

    import_record.counts = counts
    import_record.checkpoint = {"processed": len(results), "at": timezone.now().isoformat()}
    import_record.report = {"errors": errors[:100], "errors_truncated": max(0, len(errors) - 100)}
    import_record.status = (
        ProcurementAnalysisImport.Status.PARTIAL
        if counts["error"] or counts["rejected"] or counts["invalid_hash"] or counts["invalid_context"]
        else ProcurementAnalysisImport.Status.COMPLETED
    )
    import_record.finished_at = timezone.now()
    import_record.save(update_fields=["counts", "checkpoint", "report", "status", "finished_at", "updated_at"])
    if not dry_run:
        finalize_run_if_exhausted(run, actor=actor)
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_run.import_results",
        target_type="procurement_analysis_import",
        target_id=str(import_record.id),
        payload={"run_id": str(run.id), "dataset_id": str(dataset.id) if dataset else "", "dry_run": dry_run, **counts},
    )
    return import_record


@transaction.atomic
def finalize_run_if_exhausted(run: ProcurementAnalysisRun, *, actor: str = "system") -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run.pk)
    counters = refresh_run_counters(run, save=False)
    run.counters = {**(run.counters or {}), **counters}
    run.heartbeat_at = timezone.now()
    if counters["remaining"] == 0:
        run.finished_at = timezone.now()
        run.status = ProcurementAnalysisRun.Status.COMPLETED if counters["completed"] else ProcurementAnalysisRun.Status.NO_CHANGES
        if run.analysis_request_id:
            request_status = AnalysisRequest.Status.COMPLETED if counters["completed"] else AnalysisRequest.Status.NO_CHANGES
            AnalysisRequest.objects.filter(pk=run.analysis_request_id).update(
                status=request_status,
                completed_at=run.finished_at,
                metadata={**(run.analysis_request.metadata or {}), "persistent_run_counters": counters},
            )
            run.analysis_request.batches.update(
                status=AnalysisBatch.Status.COMPLETED,
                completed_count=counters["completed"],
                failed_count=counters["failed"] + counters["poison"],
                finished_at=run.finished_at,
            )
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_run.finish",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload=counters,
        )
    elif run.status not in {ProcurementAnalysisRun.Status.PAUSED, ProcurementAnalysisRun.Status.CANCELLING}:
        run.status = ProcurementAnalysisRun.Status.RUNNING
    run.last_checkpoint = {
        "completed": counters["completed"],
        "remaining": counters["remaining"],
        "updated_at": timezone.now().isoformat(),
    }
    run.save(update_fields=["status", "finished_at", "counters", "heartbeat_at", "last_checkpoint", "updated_at"])
    return run


@transaction.atomic
def pause_run(run_id: str, *, actor: str) -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run_id)
    if run.status not in ProcurementAnalysisRun.ACTIVE_STATUSES:
        raise ValueError("Run فعال نیست.")
    run.status = ProcurementAnalysisRun.Status.PAUSED
    run.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="procurement.analysis_run.pause", target_type="procurement_analysis_run", target_id=str(run.id), payload={})
    return run


@transaction.atomic
def resume_run(run_id: str, *, actor: str) -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run_id)
    if run.status != ProcurementAnalysisRun.Status.PAUSED:
        raise ValueError("فقط Run متوقف‌شده قابل ادامه است.")
    run.status = ProcurementAnalysisRun.Status.RUNNING
    run.heartbeat_at = timezone.now()
    run.save(update_fields=["status", "heartbeat_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="procurement.analysis_run.resume", target_type="procurement_analysis_run", target_id=str(run.id), payload={"checkpoint": run.last_checkpoint})
    return run


@transaction.atomic
def cancel_run(run_id: str, *, actor: str) -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run_id)
    if run.status not in ProcurementAnalysisRun.ACTIVE_STATUSES:
        raise ValueError("Run فعال نیست.")
    run.status = ProcurementAnalysisRun.Status.CANCELLING
    run.save(update_fields=["status", "updated_at"])
    run.items.filter(status__in=list(OPEN_ITEM_STATUSES)).exclude(status=ProcurementAnalysisRunItem.Status.CLAIMED).update(
        status=ProcurementAnalysisRunItem.Status.CANCELLED,
        completed_at=timezone.now(),
    )
    run.status = ProcurementAnalysisRun.Status.CANCELLED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at", "updated_at"])
    refresh_run_counters(run)
    AuditEvent.objects.create(actor=actor, action="procurement.analysis_run.cancel", target_type="procurement_analysis_run", target_id=str(run.id), payload={"future_items_only": True})
    return run


def queue_summary() -> dict[str, Any]:
    context = get_active_context()
    total = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True).exclude(
        processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED
    ).count()
    if context is None:
        return {"total_notices": total, "active_context": None, "needs_analysis": total}
    valid_notice_ids = set(
        NoticeAnalysisDraft.objects.filter(context_snapshot=context).values_list("notice_id", flat=True)
    )
    visible = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False).exclude(
        processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED
    )
    needs = 0
    valid = 0
    reanalysis = 0
    urgent = 0
    for notice in visible.prefetch_related("analysis_drafts").iterator(chunk_size=500):
        basis = notice_basis_hash(notice)
        reason = _analysis_reason(
            ProcurementAnalysisRun(context_snapshot=context, include_previously_analyzed=False), notice, basis
        )
        if reason:
            needs += 1
            if notice.id in valid_notice_ids:
                reanalysis += 1
        else:
            valid += 1
        if _deadline_priority(notice) == "urgent":
            urgent += 1
    current = active_run()
    return {
        "total_notices": total,
        "valid_analysis": valid,
        "needs_analysis": needs,
        "needs_reanalysis": reanalysis,
        "urgent": urgent,
        "active_context": {"id": str(context.id), "version": context.version, "hash": context.content_hash},
        "active_run_id": str(current.id) if current else None,
        "active_run_status": current.status if current else None,
        "active_run_counters": current.counters if current else {},
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, kind: str) -> dict[str, Any]:
    return {"kind": kind, "name": path.name, "path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _json_record(item: ProcurementAnalysisRunItem) -> dict[str, Any]:
    notice = item.notice
    source_links = list(notice.source_links.all())
    source_notices = [link.source_notice for link in source_links]
    source_payloads = [source.raw_payload or {} for source in source_notices]
    goods_group = next((str(payload.get("list", {}).get("goods_group", "")) for payload in source_payloads if payload.get("list", {}).get("goods_group")), "")
    service_group = next((str(payload.get("list", {}).get("service_group", "")) for payload in source_payloads if payload.get("list", {}).get("service_group")), "")
    latest = notice.analysis_drafts.order_by("-analyzed_at").first()
    return {
        "run_item_id": str(item.id),
        "notice_id": str(notice.id),
        "notice_type": notice.resolved_notice_type,
        "type_resolution_status": notice.type_resolution_status,
        "title": notice.title,
        "summary": notice.summary,
        "description": notice.description,
        "conditions": notice.conditions,
        "employer": notice.employer_name,
        "province": notice.province,
        "city": notice.city,
        "execution_location": notice.execution_location,
        "published_date": notice.published_date.isoformat() if notice.published_date else None,
        "submission_deadline": notice.submission_deadline.isoformat() if notice.submission_deadline else None,
        "estimated_amount_rials": str(notice.estimated_amount_rials) if notice.estimated_amount_rials is not None else None,
        "guarantee_amount_rials": str(notice.guarantee_amount_rials) if notice.guarantee_amount_rials is not None else None,
        "qualification_text": notice.qualification_text,
        "goods_group": goods_group,
        "service_group": service_group,
        "source_urls": [source.source_url for source in source_notices],
        "source_names": [source.connector.source.name for source in source_notices],
        "source_record_ids": [source.source_record_id for source in source_notices],
        "content_hash": item.notice_content_hash,
        "processing_status": notice.processing_status,
        "is_hidden": notice.is_hidden,
        "is_expired": bool(notice.submission_deadline and notice.submission_deadline < timezone.now()),
        "latest_analysis_context_version": latest.context_snapshot.version if latest else None,
        "latest_analysis_content_hash": latest.notice_content_hash if latest else None,
        "latest_review_status": latest.review_status if latest else None,
        "needs_analysis": True,
        "analysis_reason": item.analysis_reason,
        "deadline_priority": item.deadline_priority,
        "context_id": str(item.run.context_snapshot_id),
        "context_version": item.run.context_snapshot.version,
        "context_hash": item.context_hash,
    }


def _write_sql_dump(target: Path) -> dict[str, Any]:
    executable = shutil.which("pg_dump")
    if not executable:
        return {"created": False, "reason": "pg_dump_not_installed"}
    database = settings.DATABASES["default"]
    env = {**os.environ, "PGPASSWORD": str(database.get("PASSWORD") or "")}
    command = [
        executable,
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "--host", str(database.get("HOST") or "db"),
        "--port", str(database.get("PORT") or "5432"),
        "--username", str(database.get("USER") or "pdp_one"),
        "--dbname", str(database.get("NAME") or "pdp_one"),
        "--table=procurement_*",
    ]
    with gzip.open(target, "wb", compresslevel=6) as output:
        process = subprocess.run(command, env=env, stdout=output, stderr=subprocess.PIPE, check=False)
    if process.returncode:
        target.unlink(missing_ok=True)
        return {"created": False, "reason": process.stderr.decode("utf-8", errors="replace")[:1000]}
    return {"created": True}


def _restore_verify_sql(sql_gz: Path) -> dict[str, Any]:
    required = [shutil.which(name) for name in ["createdb", "psql", "dropdb"]]
    if not all(required):
        return {"attempted": False, "passed": False, "reason": "postgresql_client_tools_missing"}
    database = settings.DATABASES["default"]
    env = {**os.environ, "PGPASSWORD": str(database.get("PASSWORD") or "")}
    suffix = uuid.uuid4().hex[:10]
    temporary_db = f"pdp_procurement_restore_{suffix}"
    common = ["--host", str(database.get("HOST") or "db"), "--port", str(database.get("PORT") or "5432"), "--username", str(database.get("USER") or "pdp_one")]
    try:
        created = subprocess.run([required[0], *common, temporary_db], env=env, capture_output=True, check=False)
        if created.returncode:
            return {"attempted": True, "passed": False, "reason": created.stderr.decode("utf-8", errors="replace")[:1000]}
        with gzip.open(sql_gz, "rb") as source:
            restored = subprocess.run([required[1], *common, "--set", "ON_ERROR_STOP=1", "--dbname", temporary_db], env=env, stdin=source, capture_output=True, check=False)
        return {"attempted": True, "passed": restored.returncode == 0, "reason": restored.stderr.decode("utf-8", errors="replace")[:1000]}
    finally:
        subprocess.run([required[2], *common, "--if-exists", temporary_db], env=env, capture_output=True, check=False)


def export_dataset(dataset_id: str, *, actor: str = "system") -> ProcurementAnalysisDataset:
    dataset = ProcurementAnalysisDataset.objects.select_related("run", "context_snapshot").get(pk=dataset_id)
    dataset.status = ProcurementAnalysisDataset.Status.PREPARING
    dataset.started_at = timezone.now()
    dataset.save(update_fields=["status", "started_at", "updated_at"])
    root = Path(settings.MEDIA_ROOT) / "procurement-analysis" / str(dataset.id)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    try:
        items = dataset.run.items.select_related("notice", "run__context_snapshot").prefetch_related(
            "notice__source_links__source_notice__connector__source", "notice__analysis_drafts__context_snapshot"
        ).order_by("sequence")
        records = [_json_record(item) for item in items]
        shard_size = max(1, dataset.shard_size)
        for offset in range(0, len(records), shard_size):
            shard_number = (offset // shard_size) + 1
            path = root / f"PDP-One-Procurement-AI-Input-{dataset.id}-part-{shard_number:04d}.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                for record in records[offset: offset + shard_size]:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            files.append(_file_record(path, "jsonl"))

        csv_path = root / f"PDP-One-Procurement-AI-Review-{dataset.id}.csv.gz"
        csv_fields = ["notice_id", "notice_type", "title", "employer", "province", "submission_deadline", "analysis_reason", "deadline_priority", "content_hash"]
        with gzip.open(csv_path, "wt", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=csv_fields)
            writer.writeheader()
            for record in records:
                writer.writerow({field: record.get(field) for field in csv_fields})
        files.append(_file_record(csv_path, "csv"))

        sql_path = root / f"PDP-One-Procurement-Full-{dataset.id}.sql.gz"
        sql_result = _write_sql_dump(sql_path)
        restore_validation = {"attempted": False, "passed": False, "reason": sql_result.get("reason", "")}
        if sql_result.get("created"):
            files.append(_file_record(sql_path, "sql"))
            restore_validation = _restore_verify_sql(sql_path)

        manifest_path = root / f"PDP-One-Procurement-AI-Manifest-{dataset.id}.json"
        summary = queue_summary()
        manifest = {
            "export_id": str(dataset.id),
            "run_id": str(dataset.run_id),
            "schema_version": dataset.schema_version,
            "application_commit": os.getenv("PDP_DEPLOYED_COMMIT", ""),
            "migration_head": "procurement.0018_procurement_analysis_runs",
            "context_id": str(dataset.context_snapshot_id),
            "context_version": dataset.context_snapshot.version,
            "context_hash": dataset.context_snapshot.content_hash,
            "generated_at": timezone.now().isoformat(),
            "counts": summary,
            "records_in_files": len(records),
            "shard_count": len([file for file in files if file["kind"] == "jsonl"]),
            "files": files,
            "checkpoint": dataset.run.last_checkpoint,
            "sql_restore_validation": restore_validation,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        files.append(_file_record(manifest_path, "manifest"))

        dataset.status = ProcurementAnalysisDataset.Status.READY
        dataset.record_count = len(records)
        dataset.shard_count = len([file for file in files if file["kind"] == "jsonl"])
        dataset.files = files
        dataset.hashes = {file["name"]: file["sha256"] for file in files}
        dataset.counts = summary
        dataset.checkpoint = dataset.run.last_checkpoint
        dataset.validation = {"sql_export": sql_result, "sql_restore": restore_validation}
        dataset.application_commit = os.getenv("PDP_DEPLOYED_COMMIT", "")
        dataset.migration_head = "procurement.0018_procurement_analysis_runs"
        dataset.finished_at = timezone.now()
        dataset.last_error = ""
        dataset.save(update_fields=[
            "status", "record_count", "shard_count", "files", "hashes", "counts", "checkpoint",
            "validation", "application_commit", "migration_head", "finished_at", "last_error", "updated_at"
        ])
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_dataset.ready",
            target_type="procurement_analysis_dataset",
            target_id=str(dataset.id),
            payload={"run_id": str(dataset.run_id), "record_count": len(records), "shard_count": dataset.shard_count},
        )
    except Exception as exc:
        dataset.status = ProcurementAnalysisDataset.Status.FAILED
        dataset.last_error = str(exc)[:2000]
        dataset.finished_at = timezone.now()
        dataset.save(update_fields=["status", "last_error", "finished_at", "updated_at"])
        raise
    return dataset


def create_dataset(
    run: ProcurementAnalysisRun,
    *,
    scope: str | None = None,
    shard_size: int | None = None,
    compression: str = "gzip",
) -> ProcurementAnalysisDataset:
    if compression != "gzip":
        raise ValueError("در حال حاضر فقط gzip پشتیبانی می‌شود.")
    return ProcurementAnalysisDataset.objects.create(
        run=run,
        context_snapshot=run.context_snapshot,
        scope=scope or run.scope,
        shard_size=max(1, min(int(shard_size or run.export_shard_size), 5000)),
        compression=compression,
    )
