from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import analysis_run_service as service
from .models_analysis_runs import ProcurementAnalysisRunItem

_original_claim_run_items = service.claim_run_items


@transaction.atomic
def claim_run_items(
    run_id: str,
    *,
    worker_id: str,
    limit: int = 500,
    lease_seconds: int = 3600,
) -> list[ProcurementAnalysisRunItem]:
    """Return an unexpired claim to the same worker before claiming new work.

    Claim retrieval is intentionally idempotent for recovery from transport,
    context-window, or client retry failures. Existing tokens and attempt counts
    are preserved; only the lease is renewed. No second package is claimed while
    the worker still owns unresolved items.
    """
    normalized_worker = str(worker_id or "")[:120]
    now = timezone.now()
    max_limit = max(1, min(int(limit), 500))
    lease_until = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))

    existing_queryset = (
        ProcurementAnalysisRunItem.objects.select_for_update()
        .select_related("notice", "run", "run__context_snapshot")
        .prefetch_related("notice__source_links__source_notice")
        .filter(
            run_id=run_id,
            status=ProcurementAnalysisRunItem.Status.CLAIMED,
            claimed_by=normalized_worker,
            claim_expires_at__gte=now,
        )
        .order_by("sequence")
    )
    existing = list(existing_queryset[:max_limit])
    if existing:
        for item in existing:
            item.claim_expires_at = lease_until
            item.updated_at = now
        ProcurementAnalysisRunItem.objects.bulk_update(
            existing,
            ["claim_expires_at", "updated_at"],
            batch_size=500,
        )
        return existing

    return _original_claim_run_items(
        run_id,
        worker_id=normalized_worker,
        limit=max_limit,
        lease_seconds=lease_seconds,
    )


def install() -> None:
    service.claim_run_items = claim_run_items


install()
