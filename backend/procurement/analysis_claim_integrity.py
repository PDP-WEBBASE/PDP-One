from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent

from . import analysis_run_adaptive as adaptive
from . import analysis_run_service as service
from .analysis_utils import get_active_context
from .models_analysis_runs import ProcurementAnalysisImport, ProcurementAnalysisRun, ProcurementAnalysisRunItem


CLAIM_INTEGRITY_KEY = "_claim_integrity"
CLAIM_BASIS_SCHEMA = "compact-basis-v1"
LIVE_CONTEXT_BINDING_MODE = "latest-active-on-work-cycle"

_original_admit_newest_pending_items = adaptive.admit_newest_pending_items
_original_claim_newest_run_items = adaptive.claim_newest_run_items
_original_renew_worker_claim = adaptive.renew_worker_claim
_original_import_result_records = service.import_result_records

_CONTEXT_RETRY_STATUSES = (
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
)
_CONTEXT_REBIND_STATUSES = (
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.RETRY,
)


def analysis_claim_basis_hash(notice) -> str:
    """Hash exactly the compact semantic basis exposed to the analysis worker."""

    canonical = json.dumps(
        service._compact_basis(notice),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@transaction.atomic
def sync_run_to_active_context(run_id: str, *, actor: str = "analysis-live-context") -> dict:
    """Bind open work to the latest active Analysis Context without rewriting history.

    Completed items and drafts remain attached to the immutable Context that was
    actually used. Open work follows the latest active Context. Any in-flight
    package from a retired Context is invalidated and returned to RETRY so stale
    results cannot be silently imported after a Context switch.
    """

    run = (
        ProcurementAnalysisRun.objects.select_for_update()
        .select_related("context_snapshot")
        .get(pk=run_id)
    )
    active_context = get_active_context()
    if active_context is None:
        raise ValueError("هیچ Context فعال تحلیل تعریف نشده است.")

    previous_context = run.context_snapshot
    if previous_context_id := getattr(run, "context_snapshot_id", None):
        if previous_context_id == active_context.id:
            return {
                "changed": False,
                "run_id": str(run.id),
                "context_id": str(active_context.id),
                "context_version": active_context.version,
                "context_hash": active_context.content_hash,
                "invalidated_in_flight": 0,
                "rebound_open_items": 0,
                "binding_mode": LIVE_CONTEXT_BINDING_MODE,
            }

    now = timezone.now()
    stale_in_flight = run.items.filter(status__in=_CONTEXT_RETRY_STATUSES)
    invalidated_in_flight = stale_in_flight.count()
    if invalidated_in_flight:
        stale_in_flight.update(
            status=ProcurementAnalysisRunItem.Status.RETRY,
            context_hash=active_context.content_hash,
            claim_token=None,
            claimed_by="",
            claimed_at=None,
            claim_expires_at=None,
            last_error="analysis_context_changed_after_claim",
            screening={},
            updated_at=now,
        )

    open_items = run.items.filter(status__in=_CONTEXT_REBIND_STATUSES).exclude(
        context_hash=active_context.content_hash
    )
    rebound_open_items = open_items.count()
    if rebound_open_items:
        open_items.update(context_hash=active_context.content_hash, updated_at=now)

    metadata = dict(run.metadata or {})
    history = list(metadata.get("context_binding_history") or [])
    history.append(
        {
            "from_context_id": str(previous_context.id),
            "from_version": previous_context.version,
            "from_hash": previous_context.content_hash,
            "to_context_id": str(active_context.id),
            "to_version": active_context.version,
            "to_hash": active_context.content_hash,
            "switched_at": now.isoformat(),
            "invalidated_in_flight": invalidated_in_flight,
            "rebound_open_items": rebound_open_items,
        }
    )
    run.context_snapshot = active_context
    run.metadata = {
        **metadata,
        "context_binding_mode": LIVE_CONTEXT_BINDING_MODE,
        "active_context_version": active_context.version,
        "active_context_hash": active_context.content_hash,
        "context_binding_history": history[-20:],
    }
    run.heartbeat_at = now
    run.save(update_fields=["context_snapshot", "metadata", "heartbeat_at", "updated_at"])

    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_run.bind_latest_context",
        target_type="procurement_analysis_run",
        target_id=str(run.id),
        payload={
            "from_version": previous_context.version,
            "to_version": active_context.version,
            "from_hash": previous_context.content_hash,
            "to_hash": active_context.content_hash,
            "invalidated_in_flight": invalidated_in_flight,
            "rebound_open_items": rebound_open_items,
            "binding_mode": LIVE_CONTEXT_BINDING_MODE,
            "completed_history_preserved": True,
            "draft_only": True,
        },
    )
    return {
        "changed": True,
        "run_id": str(run.id),
        "context_id": str(active_context.id),
        "context_version": active_context.version,
        "context_hash": active_context.content_hash,
        "invalidated_in_flight": invalidated_in_flight,
        "rebound_open_items": rebound_open_items,
        "binding_mode": LIVE_CONTEXT_BINDING_MODE,
    }


@transaction.atomic
def admit_newest_pending_items(run_id: str, *, actor: str = "adaptive-analysis") -> dict:
    sync_run_to_active_context(run_id, actor=actor)
    return _original_admit_newest_pending_items(run_id, actor=actor)


@transaction.atomic
def claim_newest_run_items(
    run_id: str,
    *,
    worker_id: str,
    limit: int = adaptive.SAFE_CLAIM_LIMIT,
    lease_seconds: int = 3600,
):
    """Claim work only after rebinding the run to the latest active Context."""

    sync_run_to_active_context(run_id, actor=worker_id or "analysis-claim")
    items = _original_claim_newest_run_items(
        run_id,
        worker_id=worker_id,
        limit=limit,
        lease_seconds=lease_seconds,
    )
    if not items:
        return items

    captured_at = timezone.now()
    for item in items:
        item.screening = {
            **(item.screening or {}),
            CLAIM_INTEGRITY_KEY: {
                "schema": CLAIM_BASIS_SCHEMA,
                "hash": analysis_claim_basis_hash(item.notice),
                "captured_at": captured_at.isoformat(),
            },
        }
        item.updated_at = captured_at
    ProcurementAnalysisRunItem.objects.bulk_update(
        items,
        ["screening", "updated_at"],
        batch_size=adaptive.SAFE_CLAIM_LIMIT,
    )
    return items


@transaction.atomic
def renew_worker_claim(
    run_id: str,
    *,
    worker_id: str,
    lease_seconds: int = 3600,
    actor: str = "adaptive-analysis",
) -> dict:
    sync_run_to_active_context(run_id, actor=actor)
    return _original_renew_worker_claim(
        run_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        actor=actor,
    )


@transaction.atomic
def import_result_records(
    *,
    run_id: str,
    results: list[dict],
    actor: str,
    dataset_id: str | None = None,
    result_hash: str = "",
    dry_run: bool = False,
):
    """Reject stale Context work and preserve semantic claim integrity.

    The run is rebound to the latest active Context before any result validation.
    This invalidates claims issued under a retired Context, so their old tokens or
    Context hashes cannot be accepted after a new live Context is published.

    For current-Context claims, preserve valid claims across non-semantic hash
    churn without weakening the existing Notice/content/claim integrity contract.
    """

    sync_run_to_active_context(run_id, actor=actor)

    copied_results = [deepcopy(result) for result in results]
    normalized_results = [service._normalize_result(result) for result in copied_results]
    requested_item_ids = [
        str(result.get("run_item_id") or "")
        for result in normalized_results
        if result.get("run_item_id")
    ]
    item_map = {
        str(item.id): item
        for item in ProcurementAnalysisRunItem.objects.select_for_update()
        .select_related("notice")
        .prefetch_related("notice__source_links__source_notice")
        .filter(run_id=run_id, pk__in=requested_item_ids)
    }

    filtered_results: list[dict] = []
    changed_indexes: list[int] = []
    rebased_count = 0
    now = timezone.now()

    for index, (raw_result, result) in enumerate(zip(copied_results, normalized_results), start=1):
        item = item_map.get(str(result.get("run_item_id") or ""))
        integrity = ((item.screening or {}).get(CLAIM_INTEGRITY_KEY) if item is not None else None) or {}
        expected_basis_hash = str(integrity.get("hash") or "")

        # Let the original importer own malformed IDs/tokens/contexts and legacy
        # claims created before this compatibility layer was deployed.
        if (
            item is None
            or not expected_basis_hash
            or str(result.get("claim_token") or "") != str(item.claim_token or "")
            or str(result.get("notice_id") or "") != str(item.notice_id)
            or str(result.get("notice_content_hash") or "") != item.notice_content_hash
        ):
            filtered_results.append(raw_result)
            continue

        current_basis_hash = analysis_claim_basis_hash(item.notice)
        if current_basis_hash != expected_basis_hash:
            if not dry_run:
                item.status = ProcurementAnalysisRunItem.Status.RETRY
                item.last_error = "notice_changed_after_claim"
                item.claim_token = None
                item.claimed_by = ""
                item.claimed_at = None
                item.claim_expires_at = None
                item.updated_at = now
                item.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "claim_token",
                        "claimed_by",
                        "claimed_at",
                        "claim_expires_at",
                        "updated_at",
                    ]
                )
            changed_indexes.append(index)
            continue

        current_legacy_hash = service.notice_basis_hash(item.notice)
        if current_legacy_hash != item.notice_content_hash:
            if not dry_run:
                item.notice_content_hash = current_legacy_hash
                item.updated_at = now
                item.save(update_fields=["notice_content_hash", "updated_at"])
            if "c" in raw_result:
                raw_result["c"] = current_legacy_hash
            if "notice_content_hash" in raw_result or "c" not in raw_result:
                raw_result["notice_content_hash"] = current_legacy_hash
            rebased_count += 1

        filtered_results.append(raw_result)

    import_record = _original_import_result_records(
        run_id=run_id,
        results=filtered_results,
        actor=actor,
        dataset_id=dataset_id,
        result_hash=result_hash,
        dry_run=dry_run,
    )

    if changed_indexes:
        counts = dict(import_record.counts or {})
        counts["total"] = int(counts.get("total", len(filtered_results)) or 0) + len(changed_indexes)
        counts["invalid_hash"] = int(counts.get("invalid_hash", 0) or 0) + len(changed_indexes)

        report = dict(import_record.report or {})
        existing_errors = list(report.get("errors") or [])
        added_errors = [
            {"index": str(index), "error": "analysis_basis_changed_after_claim"}
            for index in changed_indexes
        ]
        combined_errors = existing_errors + added_errors
        previous_truncated = int(report.get("errors_truncated", 0) or 0)
        report["errors"] = combined_errors[:100]
        report["errors_truncated"] = previous_truncated + max(0, len(combined_errors) - 100)

        import_record.counts = counts
        import_record.report = report
        import_record.checkpoint = {
            "processed": len(copied_results),
            "at": timezone.now().isoformat(),
        }
        import_record.status = ProcurementAnalysisImport.Status.PARTIAL
        import_record.save(
            update_fields=["counts", "report", "checkpoint", "status", "updated_at"]
        )

    if rebased_count or changed_indexes:
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_run.claim_integrity_reconcile",
            target_type="procurement_analysis_run",
            target_id=str(run_id),
            payload={
                "legacy_hash_rebased": rebased_count,
                "semantic_basis_changed": len(changed_indexes),
                "claim_basis_schema": CLAIM_BASIS_SCHEMA,
                "draft_only": True,
                "integrity_weakened": False,
            },
        )

    return import_record


def install() -> None:
    adaptive.admit_newest_pending_items = admit_newest_pending_items
    adaptive.claim_newest_run_items = claim_newest_run_items
    adaptive.renew_worker_claim = renew_worker_claim
    service.import_result_records = import_result_records


install()
