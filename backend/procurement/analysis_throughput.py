from __future__ import annotations

from datetime import timedelta
from math import ceil
from typing import Any

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from core.models import AuditEvent

from .models_analysis import NoticeAnalysisDraft
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


SAFE_PACKAGE_SIZE = 50
MAX_PACKAGES_PER_LANE = 50

OPEN_ITEM_STATUSES = [
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
    ProcurementAnalysisRunItem.Status.RETRY,
]
RECONCILABLE_ITEM_STATUSES = [
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.RETRY,
]


def _redundant_reanalysis_queryset(run: ProcurementAnalysisRun):
    """Return explicit reanalysis items that already have an exact valid result.

    The active historical full-pending run was created with
    include_previously_analyzed=true. That means an item may still be open even
    though another exact analysis for the same Notice content and Context already
    exists. Such rows are safe to remove from the effective catch-up backlog as
    long as they are not currently claimed and no human review requested a
    revision.
    """

    exact_draft = NoticeAnalysisDraft.objects.filter(
        notice_id=OuterRef("notice_id"),
        context_snapshot_id=run.context_snapshot_id,
        notice_content_hash=OuterRef("notice_content_hash"),
    )
    needs_revision = exact_draft.filter(raw_output__human_review__decision="needs_revision")
    exact_compact = (
        ProcurementAnalysisRunItem.objects.filter(
            notice_id=OuterRef("notice_id"),
            status=ProcurementAnalysisRunItem.Status.COMPLETED,
            notice_content_hash=OuterRef("notice_content_hash"),
            context_hash=run.context_snapshot.content_hash,
            draft__isnull=True,
        )
        .exclude(pk=OuterRef("pk"))
        .exclude(result_metadata={})
    )

    return (
        run.items.filter(
            status__in=RECONCILABLE_ITEM_STATUSES,
            analysis_reason="explicit_reanalysis",
        )
        .annotate(
            has_exact_draft=Exists(exact_draft),
            needs_revision=Exists(needs_revision),
            has_exact_compact=Exists(exact_compact),
        )
        .filter(
            Q(has_exact_compact=True)
            | Q(has_exact_draft=True, needs_revision=False)
        )
    )


def count_redundant_reanalysis(run: ProcurementAnalysisRun) -> int:
    return _redundant_reanalysis_queryset(run).count()


def reconcile_redundant_reanalysis(
    run: ProcurementAnalysisRun,
    *,
    actor: str = "adaptive-analysis",
    batch_size: int = 2000,
) -> int:
    """Mark already-valid explicit reanalysis rows as skipped without deleting history."""

    total = 0
    now = timezone.now()
    while True:
        ids = list(
            _redundant_reanalysis_queryset(run)
            .values_list("id", flat=True)[: max(1, min(int(batch_size), 5000))]
        )
        if not ids:
            break
        total += run.items.filter(
            id__in=ids,
            status__in=RECONCILABLE_ITEM_STATUSES,
        ).update(
            status=ProcurementAnalysisRunItem.Status.SKIPPED,
            analysis_reason="already_valid_current_analysis",
            completed_at=now,
            claim_token=None,
            claimed_by="",
            claimed_at=None,
            claim_expires_at=None,
            last_error="",
            updated_at=now,
        )

    if total:
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_run.reconcile_redundant_reanalysis",
            target_type="procurement_analysis_run",
            target_id=str(run.id),
            payload={
                "skipped": total,
                "reason": "already_valid_current_analysis",
                "draft_only": True,
                "history_preserved": True,
            },
        )
    return total


def effective_backlog_snapshot(run: ProcurementAnalysisRun) -> dict[str, Any]:
    open_items = run.items.filter(status__in=OPEN_ITEM_STATUSES)
    reason_counts = {
        str(row["analysis_reason"] or "unspecified"): int(row["count"] or 0)
        for row in open_items.values("analysis_reason").annotate(count=Count("id"))
    }
    raw_remaining = open_items.count()
    redundant_ready = count_redundant_reanalysis(run)
    return {
        "raw_remaining": raw_remaining,
        "effective_remaining": max(0, raw_remaining - redundant_ready),
        "redundant_reanalysis_ready_to_skip": redundant_ready,
        "by_reason": reason_counts,
        "lease_expired_retry_current": open_items.filter(
            status=ProcurementAnalysisRunItem.Status.RETRY,
            last_error="claim_lease_expired",
        ).count(),
        "definition": "open run items minus exact current-content/current-context results safe to skip",
    }


def recent_throughput_snapshot(
    run: ProcurementAnalysisRun,
    *,
    window_minutes: int = 60,
) -> dict[str, Any]:
    window_minutes = max(5, min(int(window_minutes), 24 * 60))
    now = timezone.now()
    since = now - timedelta(minutes=window_minutes)

    imported = 0
    duplicate_completed = 0
    import_errors = 0
    for counts in run.imports.filter(
        dry_run=False,
        finished_at__gte=since,
    ).values_list("counts", flat=True):
        payload = counts or {}
        imported += int(payload.get("imported", 0) or 0)
        duplicate_completed += int(payload.get("duplicate", 0) or 0)
        import_errors += sum(
            int(payload.get(key, 0) or 0)
            for key in ("rejected", "invalid_hash", "invalid_context", "error")
        )

    lease_expired = 0
    for payload in AuditEvent.objects.filter(
        action="procurement.analysis_run.claim_lease_expired",
        target_type="procurement_analysis_run",
        target_id=str(run.id),
        created_at__gte=since,
    ).values_list("payload", flat=True):
        lease_expired += int((payload or {}).get("count", 0) or 0)

    return {
        "window_minutes": window_minutes,
        "since": since.isoformat(),
        "imported": imported,
        "duplicate_completed": duplicate_completed,
        "completed_delta": imported + duplicate_completed,
        "import_errors": import_errors,
        "lease_expired": lease_expired,
    }


def adaptive_throughput_policy(
    effective_remaining: int,
    *,
    recent_completed: int = 0,
    recent_lease_expired: int = 0,
) -> dict[str, Any]:
    """Return a throughput target while keeping each in-flight package bounded.

    Capacity is created by repeated Claim -> semantic analysis -> Import cycles,
    not by reserving a giant claim. This keeps the existing one-active-package per
    worker and global in-flight guardrails useful even in catch-up mode.
    """

    remaining = max(0, int(effective_remaining))
    if remaining >= 50000:
        mode, desired_lanes, target_per_hour = "emergency_catchup", 8, 20000
    elif remaining >= 40000:
        mode, desired_lanes, target_per_hour = "emergency_catchup", 8, 10000
    elif remaining >= 20000:
        mode, desired_lanes, target_per_hour = "hyper_turbo", 8, 7500
    elif remaining >= 10000:
        mode, desired_lanes, target_per_hour = "turbo", 6, 4000
    elif remaining >= 5000:
        mode, desired_lanes, target_per_hour = "fast", 4, 2000
    elif remaining >= 1000:
        mode, desired_lanes, target_per_hour = "normal", 2, 1000
    elif remaining > 0:
        mode, desired_lanes, target_per_hour = "maintenance", 1, 400
    else:
        mode, desired_lanes, target_per_hour = "idle", 0, 0

    if desired_lanes:
        base_packages = min(
            MAX_PACKAGES_PER_LANE,
            max(1, ceil(target_per_hour / (desired_lanes * SAFE_PACKAGE_SIZE))),
        )
    else:
        base_packages = 0

    completed = max(0, int(recent_completed))
    lease_expired = max(0, int(recent_lease_expired))
    sample = completed + lease_expired
    lease_expiry_ratio = (lease_expired / sample) if sample else 0.0
    backpressure = "normal"
    multiplier = 1.0
    if lease_expired >= SAFE_PACKAGE_SIZE and (completed == 0 or lease_expiry_ratio > 0.10):
        backpressure = "degraded"
        multiplier = 0.5
    elif sample >= SAFE_PACKAGE_SIZE and lease_expiry_ratio > 0.03:
        backpressure = "caution"
        multiplier = 0.75

    packages_per_lane = (
        max(1, min(MAX_PACKAGES_PER_LANE, ceil(base_packages * multiplier)))
        if base_packages
        else 0
    )
    planned_capacity = desired_lanes * SAFE_PACKAGE_SIZE * packages_per_lane

    return {
        "mode": mode,
        "effective_remaining": remaining,
        "desired_lanes": desired_lanes,
        "package_size": SAFE_PACKAGE_SIZE,
        "target_per_hour": target_per_hour,
        "max_packages_per_lane": packages_per_lane,
        "planned_capacity_per_hour": planned_capacity,
        "backpressure": backpressure,
        "recent_lease_expiry_ratio": round(lease_expiry_ratio, 4),
        "claim_contract": "one active package per worker; import successfully before next claim",
        "analysis_strategy": "semantic_fast_pass_with_deep_candidates",
        "target_is_acceptance_goal_not_guarantee": True,
    }


def analysis_throughput_snapshot(run: ProcurementAnalysisRun) -> dict[str, Any]:
    backlog = effective_backlog_snapshot(run)
    recent = recent_throughput_snapshot(run)
    policy = adaptive_throughput_policy(
        backlog["effective_remaining"],
        recent_completed=recent["completed_delta"],
        recent_lease_expired=recent["lease_expired"],
    )
    return {
        "effective_backlog": backlog,
        "recent": recent,
        "policy": policy,
    }
