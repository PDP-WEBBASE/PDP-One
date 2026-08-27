from __future__ import annotations

from typing import Any

from django.db.models import BooleanField, Case, Count, F, OuterRef, Subquery, Value, When
from django.utils import timezone

from .analysis_run_adaptive import GLOBAL_ACTIVE_CLAIM_CAP, SAFE_CLAIM_LIMIT, SEMANTIC_SLICE_SIZE
from .analysis_run_service import active_run
from .analysis_throughput import analysis_throughput_snapshot
from .models import ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


OPEN_ITEM_STATUSES = [
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
    ProcurementAnalysisRunItem.Status.RETRY,
]


def _type_counts(queryset, field: str) -> dict[str, int]:
    return {
        "tender": queryset.filter(**{field: ProcurementNotice.NoticeType.TENDER}).count(),
        "inquiry": queryset.filter(**{field: ProcurementNotice.NoticeType.INQUIRY}).count(),
        "total": queryset.count(),
    }


def _visible_notices():
    return (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        .exclude(processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
    )


def _effective_recommended_notices():
    latest_effective_recommendation = (
        NoticeAnalysisDraft.objects.filter(notice_id=OuterRef("pk"))
        .annotate(
            effective_recommendation=Case(
                When(review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED, then=Value(False)),
                default=F("is_recommended"),
                output_field=BooleanField(),
            )
        )
        .order_by("-analyzed_at", "-created_at", "-id")
        .values("effective_recommendation")[:1]
    )
    return _visible_notices().annotate(
        ai_is_recommended=Subquery(latest_effective_recommendation, output_field=BooleanField())
    ).filter(ai_is_recommended=True)


def _run_history() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in ProcurementAnalysisRun.objects.order_by("created_at")[:100]:
        counters = run.counters or {}
        rows.append(
            {
                "id": str(run.id),
                "run_type": run.run_type,
                "trigger": run.trigger,
                "status": run.status,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "total": int(counters.get("total", 0) or 0),
                "completed": int(counters.get("completed", 0) or 0),
                "recommended": int(counters.get("recommended", 0) or 0),
                "remaining": int(counters.get("remaining", 0) or 0),
            }
        )
    return rows


def procurement_analysis_statistics(run: ProcurementAnalysisRun | None = None) -> dict[str, Any]:
    run = run or active_run()
    notices = _visible_notices()
    drafts = NoticeAnalysisDraft.objects.filter(
        notice__soft_deleted_at__isnull=True,
        notice__is_hidden=False,
    ).exclude(notice__processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
    effective_recommended = _effective_recommended_notices()

    result: dict[str, Any] = {
        "generated_at": timezone.now(),
        "all_notices": _type_counts(notices, "resolved_notice_type"),
        "display_drafts": _type_counts(drafts, "notice__resolved_notice_type"),
        "display_recommended": _type_counts(effective_recommended, "resolved_notice_type"),
        "run_count": ProcurementAnalysisRun.objects.count(),
        "run_history": _run_history(),
        "active_run": None,
        "throughput": None,
        "claim_policy": {
            "priority_policy": "newest_first",
            "claim_reservation_limit": SAFE_CLAIM_LIMIT,
            "semantic_slice_size": SEMANTIC_SLICE_SIZE,
            "global_active_claim_cap": GLOBAL_ACTIVE_CLAIM_CAP,
            "one_active_reservation_per_worker": True,
            "continue_existing_reservation_after_successful_import": True,
            "checkpoint_after_each_semantic_slice": True,
            "semantic_quality_preserved_by_bounded_slices": True,
        },
    }
    if run is None:
        return result

    items = run.items.all()
    attempted = items.filter(attempts__gt=0)
    completed = items.filter(status=ProcurementAnalysisRunItem.Status.COMPLETED)
    pending = items.filter(status=ProcurementAnalysisRunItem.Status.PENDING)
    claimed = items.filter(status=ProcurementAnalysisRunItem.Status.CLAIMED)
    retry = items.filter(status=ProcurementAnalysisRunItem.Status.RETRY)
    poison = items.filter(status=ProcurementAnalysisRunItem.Status.POISON)
    failed = items.filter(status=ProcurementAnalysisRunItem.Status.FAILED)
    remaining = items.filter(status__in=OPEN_ITEM_STATUSES)
    run_recommended = completed.filter(draft__is_recommended=True)
    now = timezone.now()
    active_claimed = claimed.filter(claim_expires_at__gte=now)
    throughput = analysis_throughput_snapshot(run)

    worker_counts: dict[str, int] = {}
    for row in active_claimed.exclude(claimed_by="").values("claimed_by"):
        worker = str(row["claimed_by"] or "")
        worker_counts[worker] = worker_counts.get(worker, 0) + 1

    retry_reason_counts = {
        str(row["last_error"] or "unspecified"): int(row["count"] or 0)
        for row in retry.values("last_error").annotate(count=Count("id")).order_by("-count")
    }

    result["throughput"] = throughput
    result["active_run"] = {
        "id": str(run.id),
        "run_type": run.run_type,
        "status": run.status,
        "started_at": run.started_at,
        "heartbeat_at": run.heartbeat_at,
        "include_expired": run.include_expired,
        "include_previously_analyzed": run.include_previously_analyzed,
        "in_run": _type_counts(items, "notice__resolved_notice_type"),
        "attempted_by_chatgpt": _type_counts(attempted, "notice__resolved_notice_type"),
        "completed": _type_counts(completed, "notice__resolved_notice_type"),
        "recommended": _type_counts(run_recommended, "notice__resolved_notice_type"),
        "pending": _type_counts(pending, "notice__resolved_notice_type"),
        "claimed": _type_counts(claimed, "notice__resolved_notice_type"),
        "retry": _type_counts(retry, "notice__resolved_notice_type"),
        "poison": _type_counts(poison, "notice__resolved_notice_type"),
        "failed": _type_counts(failed, "notice__resolved_notice_type"),
        "remaining": _type_counts(remaining, "notice__resolved_notice_type"),
        "effective_remaining": throughput["effective_backlog"]["effective_remaining"],
        "retry_diagnostics": {
            "claim_lease_expired": retry.filter(last_error="claim_lease_expired").count(),
            "reason_counts": retry_reason_counts,
            "active_claimed": active_claimed.count(),
            "expired_claimed_waiting_for_recovery": claimed.filter(claim_expires_at__lt=now).count(),
            "attempts_1": remaining.filter(attempts=1).count(),
            "attempts_2": remaining.filter(attempts=2).count(),
            "attempts_3_plus": remaining.filter(attempts__gte=3).count(),
            "active_worker_item_counts": worker_counts,
        },
    }
    return result
