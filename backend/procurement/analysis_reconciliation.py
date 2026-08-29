from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.models import AuditEvent

from .analysis_run_service import active_run
from .analysis_utils import get_active_context, notice_basis_hash
from .models import ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


OPEN_ITEM_STATUSES = {
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
    ProcurementAnalysisRunItem.Status.RETRY,
}
EXPLICIT_EXCEPTION_STATUSES = {
    ProcurementAnalysisRunItem.Status.POISON,
    ProcurementAnalysisRunItem.Status.FAILED,
}


def _visible_notices():
    return (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        .exclude(processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
        .prefetch_related("source_links__source_notice")
        .order_by("created_at", "id")
    )


def _valid_draft_hashes(context_id) -> dict[Any, set[str]]:
    hashes: dict[Any, set[str]] = defaultdict(set)
    for notice_id, basis_hash in NoticeAnalysisDraft.objects.filter(
        context_snapshot_id=context_id,
        notice__soft_deleted_at__isnull=True,
        notice__is_hidden=False,
    ).values_list("notice_id", "notice_content_hash").iterator(chunk_size=2000):
        hashes[notice_id].add(str(basis_hash))
    return hashes


def _run_items_by_notice(run: ProcurementAnalysisRun | None) -> dict[Any, ProcurementAnalysisRunItem]:
    if run is None:
        return {}
    return {
        item.notice_id: item
        for item in run.items.select_related("draft").all().iterator(chunk_size=2000)
    }


def _item_is_valid_compact_result(item: ProcurementAnalysisRunItem | None, *, basis_hash: str, context_hash: str) -> bool:
    return bool(
        item
        and item.status == ProcurementAnalysisRunItem.Status.COMPLETED
        and item.notice_content_hash == basis_hash
        and item.context_hash == context_hash
        and item.result_metadata
    )


def _sample_append(samples: list[dict[str, Any]], notice: ProcurementNotice, *, basis_hash: str, reason: str) -> None:
    if len(samples) >= 25:
        return
    samples.append(
        {
            "notice_id": str(notice.id),
            "notice_type": notice.resolved_notice_type,
            "title": notice.title,
            "basis_hash": basis_hash,
            "reason": reason,
        }
    )


def _reset_item_for_current_basis(
    item: ProcurementAnalysisRunItem,
    *,
    basis_hash: str,
    context_hash: str,
    reason: str,
) -> None:
    item.notice_content_hash = basis_hash
    item.context_hash = context_hash
    item.status = ProcurementAnalysisRunItem.Status.PENDING
    item.analysis_reason = reason
    item.claim_token = None
    item.claimed_by = ""
    item.claimed_at = None
    item.claim_expires_at = None
    item.attempts = 0
    item.last_error = ""
    item.screening = {}
    item.result_metadata = {}
    item.draft = None
    item.completed_at = None
    item.save(
        update_fields=[
            "notice_content_hash",
            "context_hash",
            "status",
            "analysis_reason",
            "claim_token",
            "claimed_by",
            "claimed_at",
            "claim_expires_at",
            "attempts",
            "last_error",
            "screening",
            "result_metadata",
            "draft",
            "completed_at",
            "updated_at",
        ]
    )


@transaction.atomic
def procurement_analysis_integrity_snapshot(
    *,
    repair: bool = False,
    actor: str = "system",
) -> dict[str, Any]:
    """Reconcile every visible procurement notice against the active analysis context.

    Historical drafts are never deleted. Repair only attaches missing work to the existing
    active run, or resets a stale/non-leased run item to PENDING for the current basis.
    Active, non-expired claims are never stolen or rewritten.
    """

    context = get_active_context()
    if context is None:
        raise ValueError("هیچ Context فعال تحلیل تعریف نشده است.")

    run = active_run()
    draft_hashes = _valid_draft_hashes(context.id)
    run_items = _run_items_by_notice(run)
    now = timezone.now()
    next_sequence = 0
    if run is not None:
        next_sequence = int(run.items.aggregate(value=Max("sequence"))["value"] or 0)

    counts = {
        "total_visible": 0,
        "validly_analyzed": 0,
        "open_work": 0,
        "explicit_exception": 0,
        "orphan": 0,
        "stale_run_item": 0,
        "deferred_active_claim": 0,
        "repaired_created": 0,
        "repaired_reset": 0,
    }
    orphan_samples: list[dict[str, Any]] = []
    stale_samples: list[dict[str, Any]] = []
    create_buffer: list[ProcurementAnalysisRunItem] = []

    for notice in _visible_notices().iterator(chunk_size=500):
        counts["total_visible"] += 1
        basis_hash = notice_basis_hash(notice)
        item = run_items.get(notice.id)
        has_valid_draft = basis_hash in draft_hashes.get(notice.id, set())
        has_valid_compact = _item_is_valid_compact_result(
            item,
            basis_hash=basis_hash,
            context_hash=context.content_hash,
        )
        if has_valid_draft or has_valid_compact:
            counts["validly_analyzed"] += 1
            continue

        if item is not None:
            item_matches_basis = (
                item.notice_content_hash == basis_hash
                and item.context_hash == context.content_hash
            )
            if item_matches_basis and item.status in OPEN_ITEM_STATUSES:
                counts["open_work"] += 1
                continue
            if item_matches_basis and item.status in EXPLICIT_EXCEPTION_STATUSES:
                counts["explicit_exception"] += 1
                continue

            counts["stale_run_item"] += 1
            _sample_append(stale_samples, notice, basis_hash=basis_hash, reason="stale_or_terminal_run_item")
            active_claim = (
                item.status == ProcurementAnalysisRunItem.Status.CLAIMED
                and item.claim_expires_at is not None
                and item.claim_expires_at >= now
            )
            if active_claim:
                counts["deferred_active_claim"] += 1
                continue
            if repair and run is not None:
                reason = (
                    "analysis_context_changed"
                    if item.context_hash != context.content_hash
                    else "notice_content_changed"
                    if item.notice_content_hash != basis_hash
                    else "reconciliation_terminal_without_valid_result"
                )
                _reset_item_for_current_basis(
                    item,
                    basis_hash=basis_hash,
                    context_hash=context.content_hash,
                    reason=reason,
                )
                counts["repaired_reset"] += 1
                counts["open_work"] += 1
                continue

        counts["orphan"] += 1
        _sample_append(orphan_samples, notice, basis_hash=basis_hash, reason="missing_from_active_run")
        if repair and run is not None:
            next_sequence += 1
            create_buffer.append(
                ProcurementAnalysisRunItem(
                    run=run,
                    notice=notice,
                    notice_content_hash=basis_hash,
                    context_hash=context.content_hash,
                    status=ProcurementAnalysisRunItem.Status.PENDING,
                    analysis_reason="reconciliation_missing_from_active_run",
                    deadline_priority="unknown",
                    shard_number=((next_sequence - 1) // max(1, run.export_shard_size)) + 1,
                    sequence=next_sequence,
                )
            )
            if len(create_buffer) >= 500:
                ProcurementAnalysisRunItem.objects.bulk_create(create_buffer, ignore_conflicts=True)
                counts["repaired_created"] += len(create_buffer)
                create_buffer.clear()

    if create_buffer:
        ProcurementAnalysisRunItem.objects.bulk_create(create_buffer, ignore_conflicts=True)
        counts["repaired_created"] += len(create_buffer)

    if repair and run is not None:
        run.refresh_from_db(fields=["metadata", "counters", "last_checkpoint", "heartbeat_at"])
        total = run.items.count()
        remaining = run.items.filter(status__in=OPEN_ITEM_STATUSES).count()
        run.metadata = {
            **(run.metadata or {}),
            "analysis_reconciliation": {
                "last_full_at": now.isoformat(),
                "analysis_orphan_count_before_repair": counts["orphan"],
                "repaired_created": counts["repaired_created"],
                "repaired_reset": counts["repaired_reset"],
                "deferred_active_claim": counts["deferred_active_claim"],
            },
        }
        run.counters = {**(run.counters or {}), "total": total, "remaining": remaining}
        run.last_checkpoint = {
            **(run.last_checkpoint or {}),
            "reconciled_at": now.isoformat(),
            "reconciled_total": counts["total_visible"],
        }
        run.heartbeat_at = now
        run.save(update_fields=["metadata", "counters", "last_checkpoint", "heartbeat_at", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_integrity.reconcile",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={
                **counts,
                "context_version": context.version,
                "context_hash": context.content_hash,
                "zero_loss_invariant": True,
            },
        )

    unresolved = counts["orphan"] + counts["deferred_active_claim"]
    if repair and run is not None:
        unresolved = max(0, counts["orphan"] - counts["repaired_created"]) + counts["deferred_active_claim"]

    denominator = max(1, counts["total_visible"])
    covered = counts["validly_analyzed"] + counts["open_work"] + counts["explicit_exception"]
    if repair and run is not None:
        covered += counts["repaired_created"]
    coverage_percent = round(min(100.0, (covered / denominator) * 100.0), 4)

    return {
        "generated_at": now,
        "context_version": context.version,
        "context_hash": context.content_hash,
        "active_run_id": str(run.id) if run else None,
        "repair_requested": repair,
        "repair_available": run is not None,
        "zero_loss_invariant": "every visible current-basis notice must be analyzed, explicitly queued, or explicitly excepted",
        "analysis_orphan_count": unresolved,
        "coverage_percent": coverage_percent,
        "counts": counts,
        "orphan_samples": orphan_samples,
        "stale_samples": stale_samples,
        "healthy": unresolved == 0,
    }
