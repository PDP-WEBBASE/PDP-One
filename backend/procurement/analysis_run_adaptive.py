from __future__ import annotations

import json
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import F, Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import AuditEvent

from .analysis_run_service import (
    _analysis_reason,
    _candidate_queryset,
    _compact_basis,
    _deadline_priority,
    finalize_run_if_exhausted,
)
from .analysis_throughput import reconcile_redundant_reanalysis
from .analysis_utils import notice_basis_hash
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


ADMISSION_OVERLAP = timedelta(minutes=10)
REANALYSIS_RECONCILE_INTERVAL = timedelta(minutes=10)
SAFE_CLAIM_LIMIT = 50
GLOBAL_ACTIVE_CLAIM_CAP = 400


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
    """Admit notices that arrived after a persistent run started.

    Persistent runs used to be a frozen snapshot. That allowed a large backlog to
    block newly extracted notices for days. This admission step keeps the active
    run open to fresh notices while preserving all completed draft results.
    """

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
def claim_newest_run_items(
    run_id: str,
    *,
    worker_id: str,
    limit: int = SAFE_CLAIM_LIMIT,
    lease_seconds: int = 3600,
) -> list[ProcurementAnalysisRunItem]:
    """Claim the freshest safe package while allowing sequential packages.

    One worker may own only one in-flight package and the run retains a bounded
    global in-flight pool. After the package is successfully imported, the same
    worker can immediately request the next package. Throughput therefore scales
    through repeated Claim -> semantic analysis -> Import cycles instead of one
    oversized reservation that is likely to expire.
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
        if run.status in {
            ProcurementAnalysisRun.Status.COMPLETED,
            ProcurementAnalysisRun.Status.NO_CHANGES,
        }:
            return []

    worker_has_active_claim = run.items.filter(
        status=ProcurementAnalysisRunItem.Status.CLAIMED,
        claimed_by=worker_key,
        claim_expires_at__gte=now,
    ).exists()
    if worker_has_active_claim:
        return []

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

    candidates = list(queryset[:requested_limit])
    selected: list[ProcurementAnalysisRunItem] = []
    estimated_payload_chars = 2
    max_payload_chars = 120_000
    for candidate in candidates:
        estimate = len(
            json.dumps(
                {
                    "i": str(candidate.id),
                    "n": str(candidate.notice_id),
                    "c": candidate.notice_content_hash,
                    "ar": candidate.analysis_reason,
                    "dp": candidate.deadline_priority,
                    "b": _compact_basis(candidate.notice),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ) + 48
        if selected and estimated_payload_chars + estimate > max_payload_chars:
            break
        selected.append(candidate)
        estimated_payload_chars += estimate

    expires = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))
    for item in selected:
        item.new_claim_token()
        item.status = ProcurementAnalysisRunItem.Status.CLAIMED
        item.claimed_by = worker_key
        item.claimed_at = now
        item.claim_expires_at = expires
        item.attempts += 1
        item.last_error = ""
        item.updated_at = now
    if selected:
        ProcurementAnalysisRunItem.objects.bulk_update(
            selected,
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
            "safe_package_size": SAFE_CLAIM_LIMIT,
            "global_active_claim_cap": GLOBAL_ACTIVE_CLAIM_CAP,
        }
        run.save(update_fields=["status", "heartbeat_at", "metadata", "updated_at"])
    return selected
