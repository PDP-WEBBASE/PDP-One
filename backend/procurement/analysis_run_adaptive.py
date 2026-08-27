from __future__ import annotations

from datetime import timedelta

from django.db import connection, transaction
from django.db.models import F, Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import AuditEvent

from .analysis_run_service import (
    _analysis_reason,
    _candidate_queryset,
    _deadline_priority,
    finalize_run_if_exhausted,
)
from .analysis_throughput import reconcile_redundant_reanalysis
from .analysis_utils import notice_basis_hash
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


ADMISSION_OVERLAP = timedelta(minutes=10)
REANALYSIS_RECONCILE_INTERVAL = timedelta(minutes=10)
# A worker reserves a larger operational window, but ChatGPT only receives one
# bounded semantic slice at a time. This reduces claim/scheduler overhead without
# turning 500 records into one model prompt.
SAFE_CLAIM_LIMIT = 500
SEMANTIC_SLICE_SIZE = 50
GLOBAL_ACTIVE_CLAIM_CAP = 4000


def _admission_since(run: ProcurementAnalysisRun):
    raw = str((run.metadata or {}).get("last_admission_check_at") or "")
    parsed = parse_datetime(raw) if raw else None
    base = parsed or run.started_at or run.created_at
    return base - ADMISSION_OVERLAP


def _should_reconcile_reanalysis(run: ProcurementAnalysisRun, now) -> bool:
    raw = str((run.metadata or {}).get("last_reanalysis_reconciliation_at") or "")
    parsed = parse_datetime(raw) if raw else None
    return parsed is None or parsed <= now - REANALYSIS_RECONCILE_INTERVAL


def _maybe_reconcile_reanalysis(run: ProcurementAnalysisRun, now) -> int:
    """Scan exact-valid reanalysis at a bounded cadence, not on every package."""

    if not _should_reconcile_reanalysis(run, now):
        return 0
    reconciled = reconcile_redundant_reanalysis(run, actor="adaptive-analysis")
    run.metadata = {
        **(run.metadata or {}),
        "last_reanalysis_reconciliation_at": now.isoformat(),
        "last_reanalysis_reconciliation_skipped": reconciled,
    }
    run.save(update_fields=["metadata", "updated_at"])
    return reconciled


@transaction.atomic
def admit_newest_pending_items(run_id: str, *, actor: str = "adaptive-analysis") -> dict:
    """Admit notices that arrived after a persistent run started."""

    run = ProcurementAnalysisRun.objects.select_for_update().select_related("context_snapshot").get(pk=run_id)
    if run.status in {
        ProcurementAnalysisRun.Status.PAUSED,
        ProcurementAnalysisRun.Status.CANCELLING,
        ProcurementAnalysisRun.Status.CANCELLED,
        ProcurementAnalysisRun.Status.COMPLETED,
        ProcurementAnalysisRun.Status.NO_CHANGES,
        ProcurementAnalysisRun.Status.FAILED,
    }:
        return {"admitted": 0, "reason": "run_not_accepting_new_items"}

    cutoff = timezone.now()
    since = _admission_since(run)
    queryset = (
        _candidate_queryset(run)
        .filter(last_seen_at__gte=since)
        .exclude(persistent_analysis_items__run_id=run.id)
        .order_by(
            F("last_seen_at").desc(nulls_last=True),
            F("published_date").desc(nulls_last=True),
            F("created_at").desc(nulls_last=True),
            F("id").desc(),
        )
    )

    sequence = int(run.items.aggregate(value=Max("sequence"))["value"] or 0)
    admitted = 0
    buffer: list[ProcurementAnalysisRunItem] = []
    for notice in queryset.iterator(chunk_size=500):
        basis_hash = notice_basis_hash(notice)
        reason = _analysis_reason(run, notice, basis_hash)
        if reason is None:
            continue
        sequence += 1
        admitted += 1
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

    run.metadata = {
        **(run.metadata or {}),
        "adaptive_admission": True,
        "priority_policy": "newest_first",
        "last_admission_check_at": cutoff.isoformat(),
    }
    run.heartbeat_at = cutoff
    run.save(update_fields=["metadata", "heartbeat_at", "updated_at"])

    if admitted:
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_run.admit_fresh_items",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={
                "admitted": admitted,
                "since": since.isoformat(),
                "cutoff": cutoff.isoformat(),
                "priority_policy": "newest_first",
                "draft_only": True,
            },
        )
    return {
        "admitted": admitted,
        "since": since.isoformat(),
        "cutoff": cutoff.isoformat(),
        "priority_policy": "newest_first",
    }


def _expire_stale_claims(run: ProcurementAnalysisRun, now) -> int:
    stale = run.items.filter(
        status=ProcurementAnalysisRunItem.Status.CLAIMED,
        claim_expires_at__lt=now,
    )
    count = stale.count()
    if count:
        stale.update(
            status=ProcurementAnalysisRunItem.Status.RETRY,
            claim_token=None,
            claimed_by="",
            claimed_at=None,
            claim_expires_at=None,
            last_error="claim_lease_expired",
            updated_at=now,
        )
    return count


@transaction.atomic
def renew_worker_claim(
    run_id: str,
    *,
    worker_id: str,
    lease_seconds: int = 3600,
    actor: str = "adaptive-analysis",
) -> dict:
    """Extend only the caller worker's still-active reserved claim window."""

    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run_id)
    now = timezone.now()
    worker_key = worker_id[:120]
    extension_seconds = max(60, min(int(lease_seconds), 3600))
    new_expiry = now + timedelta(seconds=extension_seconds)
    active = run.items.filter(
        status=ProcurementAnalysisRunItem.Status.CLAIMED,
        claimed_by=worker_key,
        claim_expires_at__gte=now,
    )
    renewed = active.update(claim_expires_at=new_expiry, updated_at=now)
    if renewed:
        run.heartbeat_at = now
        run.save(update_fields=["heartbeat_at", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_run.claim_lease_renewed",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={
                "worker": worker_key,
                "renewed_items": renewed,
                "lease_seconds": extension_seconds,
                "new_expiry": new_expiry.isoformat(),
            },
        )
    return {
        "run_id": str(run.id),
        "worker_id": worker_key,
        "renewed_items": renewed,
        "lease_seconds": extension_seconds,
        "claim_expires_at": new_expiry.isoformat() if renewed else None,
        "expired_claims_resurrected": False,
    }


def _active_worker_slice(run: ProcurementAnalysisRun, worker_key: str, now) -> list[ProcurementAnalysisRunItem]:
    """Return the next bounded semantic slice from an existing reservation."""

    queryset = (
        run.items.select_related("notice")
        .prefetch_related("notice__source_links__source_notice")
        .filter(
            status=ProcurementAnalysisRunItem.Status.CLAIMED,
            claimed_by=worker_key,
            claim_expires_at__gte=now,
        )
        .order_by("claimed_at", "sequence")
    )
    return list(queryset[:SEMANTIC_SLICE_SIZE])


@transaction.atomic
def claim_newest_run_items(
    run_id: str,
    *,
    worker_id: str,
    limit: int = SAFE_CLAIM_LIMIT,
    lease_seconds: int = 3600,
) -> list[ProcurementAnalysisRunItem]:
    """Reserve up to 500 items, returning only the next 50-item semantic slice.

    The first call for an idle worker reserves an operational window of up to
    SAFE_CLAIM_LIMIT items. Only SEMANTIC_SLICE_SIZE items are returned to ChatGPT.
    After those results are imported/checkpointed, the next call returns the next
    still-claimed slice from the same reservation. This preserves semantic quality
    while reducing repeated claim-allocation overhead.
    """

    run = ProcurementAnalysisRun.objects.select_for_update().select_related("context_snapshot").get(pk=run_id)
    if run.status == ProcurementAnalysisRun.Status.PAUSED:
        return []
    if run.status in {ProcurementAnalysisRun.Status.CANCELLING, ProcurementAnalysisRun.Status.CANCELLED}:
        return []
    if run.status not in {ProcurementAnalysisRun.Status.RUNNING, ProcurementAnalysisRun.Status.WAITING_FOR_RESULTS}:
        raise ValueError("Run در وضعیت قابل Claim نیست.")

    now = timezone.now()
    worker_key = worker_id[:120]
    expired = _expire_stale_claims(run, now)
    if expired:
        AuditEvent.objects.create(
            actor="analysis-claim-guard",
            action="procurement.analysis_run.claim_lease_expired",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={"count": expired, "worker": worker_key},
        )

    reconciled = _maybe_reconcile_reanalysis(run, now)
    if reconciled:
        run = finalize_run_if_exhausted(run, actor="adaptive-analysis")
        if run.status in {ProcurementAnalysisRun.Status.COMPLETED, ProcurementAnalysisRun.Status.NO_CHANGES}:
            return []

    existing_slice = _active_worker_slice(run, worker_key, now)
    if existing_slice:
        return existing_slice

    active_claims = run.items.filter(
        status=ProcurementAnalysisRunItem.Status.CLAIMED,
        claim_expires_at__gte=now,
    ).count()
    available_global_slots = max(0, GLOBAL_ACTIVE_CLAIM_CAP - active_claims)
    if available_global_slots <= 0:
        return []

    requested_limit = max(1, min(int(limit), SAFE_CLAIM_LIMIT, available_global_slots))
    queryset = (
        run.items.select_related("notice")
        .prefetch_related("notice__source_links__source_notice")
        .filter(status__in=[ProcurementAnalysisRunItem.Status.PENDING, ProcurementAnalysisRunItem.Status.RETRY])
        .order_by(
            F("notice__last_seen_at").desc(nulls_last=True),
            F("notice__published_date").desc(nulls_last=True),
            F("notice__created_at").desc(nulls_last=True),
            "sequence",
        )
    )
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()

    reserved = list(queryset[:requested_limit])
    expires = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))
    for item in reserved:
        item.new_claim_token()
        item.status = ProcurementAnalysisRunItem.Status.CLAIMED
        item.claimed_by = worker_key
        item.claimed_at = now
        item.claim_expires_at = expires
        item.attempts += 1
        item.last_error = ""
        item.updated_at = now

    if reserved:
        ProcurementAnalysisRunItem.objects.bulk_update(
            reserved,
            [
                "claim_token",
                "status",
                "claimed_by",
                "claimed_at",
                "claim_expires_at",
                "attempts",
                "last_error",
                "updated_at",
            ],
            batch_size=SAFE_CLAIM_LIMIT,
        )
        run.status = ProcurementAnalysisRun.Status.WAITING_FOR_RESULTS
        run.heartbeat_at = now
        run.metadata = {
            **(run.metadata or {}),
            "throughput_controller": "adaptive-packages-v2",
            "safe_package_size": SEMANTIC_SLICE_SIZE,
            "claim_reservation_size": SAFE_CLAIM_LIMIT,
            "semantic_micro_batch_size": SEMANTIC_SLICE_SIZE,
            "global_active_claim_cap": GLOBAL_ACTIVE_CLAIM_CAP,
        }
        run.save(update_fields=["status", "heartbeat_at", "metadata", "updated_at"])

    return _active_worker_slice(run, worker_key, now)
