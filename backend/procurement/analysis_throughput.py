from __future__ import annotations

from collections import Counter
from datetime import timedelta
from math import ceil
from typing import Any

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from core.models import AuditEvent

from .models_analysis import NoticeAnalysisDraft
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


# Hyper Turbo V2 deliberately separates the semantic micro-batch from the
# per-lane hourly work window. ChatGPT still receives bounded 50-item claims,
# while the runtime authorizes repeated claims up to an aggressive hourly budget.
# This avoids one giant 1000-item reservation/context while preserving the
# requested 1000 analyses/hour/lane ceiling.
SAFE_PACKAGE_SIZE = 50
MAX_PACKAGES_PER_LANE = 20
MAX_ANALYSIS_LANES = 8
PER_LANE_HOURLY_CEILING = 1000
MIN_OPERATIONAL_SLA_PER_HOUR = 2000
PREFERRED_SUSTAINED_MIN_PER_HOUR = 4000
PREFERRED_SUSTAINED_MAX_PER_HOUR = 6000

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
    import_error_buckets = {
        "rejected": 0,
        "invalid_hash": 0,
        "invalid_context": 0,
        "error": 0,
    }
    error_classes: Counter[str] = Counter()
    recent_imports: list[dict[str, Any]] = []

    import_rows = run.imports.filter(
        dry_run=False,
        finished_at__gte=since,
    ).order_by("-finished_at").values(
        "id",
        "status",
        "counts",
        "report",
        "finished_at",
    )
    for position, row in enumerate(import_rows):
        counts = row.get("counts") or {}
        imported += int(counts.get("imported", 0) or 0)
        duplicate_completed += int(counts.get("duplicate", 0) or 0)
        row_error_total = 0
        for key in import_error_buckets:
            value = int(counts.get(key, 0) or 0)
            import_error_buckets[key] += value
            row_error_total += value
        import_errors += row_error_total

        report = row.get("report") or {}
        row_classes: Counter[str] = Counter()
        for error in report.get("errors") or []:
            error_name = str((error or {}).get("error") or "unknown")
            row_classes[error_name] += 1
            error_classes[error_name] += 1

        if position < 20:
            recent_imports.append(
                {
                    "id": str(row["id"]),
                    "status": row.get("status"),
                    "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
                    "counts": {
                        "total": int(counts.get("total", 0) or 0),
                        "imported": int(counts.get("imported", 0) or 0),
                        "duplicate": int(counts.get("duplicate", 0) or 0),
                        "rejected": int(counts.get("rejected", 0) or 0),
                        "invalid_hash": int(counts.get("invalid_hash", 0) or 0),
                        "invalid_context": int(counts.get("invalid_context", 0) or 0),
                        "error": int(counts.get("error", 0) or 0),
                    },
                    "error_classes_sampled": dict(sorted(row_classes.items())),
                    "errors_truncated": int(report.get("errors_truncated", 0) or 0),
                }
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
        "import_error_buckets": import_error_buckets,
        "import_error_classes_sampled": dict(sorted(error_classes.items())),
        "recent_imports": recent_imports,
        "lease_expired": lease_expired,
    }


def _aggressive_claim_window(effective_remaining: int) -> int:
    """Return the V2 per-lane hourly work window.

    This is intentionally more aggressive than V1 even at medium/low backlog.
    It is a work budget, not one giant semantic prompt/claim. The worker consumes
    the window through SAFE_PACKAGE_SIZE micro-batches with import/checkpoint
    between packages, so interruption recovery remains bounded.
    """

    remaining = max(0, int(effective_remaining))
    if remaining >= 10000:
        return 1000
    if remaining >= 5000:
        return 750
    if remaining >= 2000:
        return 500
    if remaining >= 500:
        return 500
    if remaining > 0:
        return min(250, remaining)
    return 0


def _desired_lanes(effective_remaining: int) -> int:
    """Keep all eight lanes admitted until the queue is genuinely near empty."""

    remaining = max(0, int(effective_remaining))
    if remaining >= 500:
        return MAX_ANALYSIS_LANES
    if remaining > 0:
        return min(MAX_ANALYSIS_LANES, max(1, ceil(remaining / SAFE_PACKAGE_SIZE)))
    return 0


def adaptive_throughput_policy(
    effective_remaining: int,
    *,
    recent_completed: int = 0,
    recent_lease_expired: int = 0,
) -> dict[str, Any]:
    """Return the Hyper Turbo V2 closed-loop throughput policy.

    Capacity is created by repeated bounded Claim -> semantic analysis -> Import
    cycles. Each lane may consume up to 1000 records/hour at high backlog, while
    semantic quality and recovery remain protected by 50-item micro-batches.
    """

    remaining = max(0, int(effective_remaining))
    desired_lanes = _desired_lanes(remaining)
    claim_window = _aggressive_claim_window(remaining)

    if remaining >= 10000:
        mode, target_per_hour = "hyper_turbo_v2", 8000
    elif remaining >= 5000:
        mode, target_per_hour = "turbo_v2", 6000
    elif remaining >= 2000:
        mode, target_per_hour = "fast_v2", 4000
    elif remaining >= 500:
        mode, target_per_hour = "catchup_v2", 2000
    elif remaining > 0:
        mode, target_per_hour = "drain_v2", remaining
    else:
        mode, target_per_hour = "idle", 0

    if desired_lanes and claim_window:
        base_packages = min(
            MAX_PACKAGES_PER_LANE,
            max(1, ceil(min(PER_LANE_HOURLY_CEILING, claim_window) / SAFE_PACKAGE_SIZE)),
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

    if target_per_hour >= PREFERRED_SUSTAINED_MAX_PER_HOUR:
        sla_state = "preferred_or_better"
    elif target_per_hour >= MIN_OPERATIONAL_SLA_PER_HOUR:
        sla_state = "minimum_sla_or_better"
    elif target_per_hour > 0:
        sla_state = "draining_small_backlog"
    else:
        sla_state = "idle"

    return {
        "mode": mode,
        "effective_remaining": remaining,
        "desired_lanes": desired_lanes,
        "package_size": SAFE_PACKAGE_SIZE,
        "micro_batch_size": SAFE_PACKAGE_SIZE,
        "claim_window_target_per_lane": claim_window,
        "per_lane_hourly_ceiling": PER_LANE_HOURLY_CEILING,
        "target_per_hour": target_per_hour,
        "minimum_operational_sla_per_hour": MIN_OPERATIONAL_SLA_PER_HOUR,
        "preferred_sustained_per_hour": {
            "min": PREFERRED_SUSTAINED_MIN_PER_HOUR,
            "max": PREFERRED_SUSTAINED_MAX_PER_HOUR,
        },
        "max_packages_per_lane": packages_per_lane,
        "planned_capacity_per_hour": planned_capacity,
        "sla_state": sla_state,
        "backpressure": backpressure,
        "recent_lease_expiry_ratio": round(lease_expiry_ratio, 4),
        "claim_contract": "one active micro-batch per worker; import/checkpoint successfully before the next micro-batch",
        "window_contract": "runtime-authorized per-lane hourly work window; never one giant semantic prompt",
        "analysis_strategy": "semantic_micro_batches_with_continuous_import_checkpoint",
        "scheduler_expectation": "keep all eight lanes admitted while effective_remaining >= 500",
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
