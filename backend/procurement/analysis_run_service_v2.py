from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from core.models import AuditEvent

from . import analysis_run_service as legacy
from .models import ProcurementNotice
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem

_legacy_claim_run_items = legacy.claim_run_items
_legacy_import_result_records = legacy.import_result_records
_legacy_cancel_run = legacy.cancel_run
_legacy_candidate_queryset = legacy._candidate_queryset
_legacy_export_dataset = legacy.export_dataset
_legacy_refresh_run_counters = legacy.refresh_run_counters


def _candidate_queryset(run: ProcurementAnalysisRun):
    return _legacy_candidate_queryset(run).prefetch_related("analysis_drafts")


def refresh_run_counters(run: ProcurementAnalysisRun, *, save: bool = True) -> dict[str, int]:
    counters = _legacy_refresh_run_counters(run, save=False)
    completed_items = run.items.filter(draft__isnull=False).select_related("draft")
    recommended = completed_items.filter(draft__is_recommended=True).count()
    urgent_drafts = completed_items.filter(draft__priority="urgent").count()
    needs_information = 0
    for raw_output in completed_items.values_list("draft__raw_output", flat=True).iterator(chunk_size=500):
        if (raw_output or {}).get("missing_information"):
            needs_information += 1
    counters.update({
        "ai_drafts": counters.get("completed", 0),
        "deep_analyzed": counters.get("completed", 0),
        "recommended": recommended,
        "not_recommended": max(0, counters.get("completed", 0) - recommended),
        "urgent_drafts": urgent_drafts,
        "needs_information": needs_information,
    })
    if save:
        run.counters = {**(run.counters or {}), **counters}
        run.heartbeat_at = timezone.now()
        run.save(update_fields=["counters", "heartbeat_at", "updated_at"])
    return counters


@transaction.atomic
def claim_run_items(
    run_id: str,
    *,
    worker_id: str,
    limit: int = 25,
    lease_seconds: int = 900,
) -> list[ProcurementAnalysisRunItem]:
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
    run.items.filter(
        status=ProcurementAnalysisRunItem.Status.RETRY,
        attempts__gte=run.max_retries_per_record + 1,
    ).update(
        status=ProcurementAnalysisRunItem.Status.POISON,
        claim_token=None,
        claimed_by="",
        claimed_at=None,
        claim_expires_at=None,
        completed_at=now,
        last_error="max_retries_exceeded",
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
            "claim_token",
            "status",
            "claimed_by",
            "claimed_at",
            "claim_expires_at",
            "attempts",
            "updated_at",
        ])
    if selected:
        run.status = ProcurementAnalysisRun.Status.WAITING_FOR_RESULTS
        run.heartbeat_at = now
        run.save(update_fields=["status", "heartbeat_at", "updated_at"])
    return selected


@transaction.atomic
def import_result_records(*args: Any, **kwargs: Any):
    """Provide the transaction required by select_for_update in the importer."""
    return _legacy_import_result_records(*args, **kwargs)


@transaction.atomic
def cancel_run(run_id: str, *, actor: str) -> ProcurementAnalysisRun:
    run = ProcurementAnalysisRun.objects.select_for_update().get(pk=run_id)
    if run.status not in ProcurementAnalysisRun.ACTIVE_STATUSES:
        raise ValueError("Run فعال نیست.")
    run.status = ProcurementAnalysisRun.Status.CANCELLING
    run.save(update_fields=["status", "updated_at"])
    run.items.filter(
        status__in=[
            ProcurementAnalysisRunItem.Status.PENDING,
            ProcurementAnalysisRunItem.Status.CLAIMED,
            ProcurementAnalysisRunItem.Status.SCREENED,
            ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
            ProcurementAnalysisRunItem.Status.RETRY,
        ]
    ).update(
        status=ProcurementAnalysisRunItem.Status.CANCELLED,
        claim_token=None,
        claimed_by="",
        claimed_at=None,
        claim_expires_at=None,
        completed_at=timezone.now(),
        last_error="cancelled_by_operator",
    )
    run.status = ProcurementAnalysisRun.Status.CANCELLED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at", "updated_at"])
    legacy.refresh_run_counters(run)
    AuditEvent.objects.create(
        actor=actor,
        action="procurement.analysis_run.cancel",
        target_type="procurement_analysis_run",
        target_id=str(run.id),
        payload={"future_items_only": True, "healthy_results_preserved": True},
    )
    return run


_EXTERNAL_FK_BLOCK = re.compile(
    r"(?ms)^--\n-- Name: .*?; Type: FK CONSTRAINT;.*?\n--\n\nALTER TABLE ONLY .*?;\n"
)


def _remove_external_foreign_keys(sql_text: str) -> tuple[str, int]:
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        block = match.group(0)
        if re.search(r"REFERENCES\s+(?:public\.)?procurement_", block, flags=re.IGNORECASE):
            return block
        removed += 1
        return ""

    return _EXTERNAL_FK_BLOCK.sub(replace, sql_text), removed


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
        "--no-comments",
        "--format=plain",
        "--host",
        str(database.get("HOST") or "db"),
        "--port",
        str(database.get("PORT") or "5432"),
        "--username",
        str(database.get("USER") or "pdp_one"),
        "--dbname",
        str(database.get("NAME") or "pdp_one"),
        "--table=procurement_*",
    ]
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="pdp-procurement-", suffix=".sql", delete=False) as temporary:
            temporary_name = temporary.name
            process = subprocess.run(command, env=env, stdout=temporary, stderr=subprocess.PIPE, check=False)
        if process.returncode:
            return {
                "created": False,
                "reason": process.stderr.decode("utf-8", errors="replace")[:1000],
            }
        source = Path(temporary_name).read_text(encoding="utf-8", errors="replace")
        filtered, removed = _remove_external_foreign_keys(source)
        with gzip.open(target, "wt", encoding="utf-8", compresslevel=6) as output:
            output.write(filtered)
        return {
            "created": True,
            "external_foreign_keys_removed": removed,
            "module_tables_only": True,
        }
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _procurement_table_counts() -> dict[str, int]:
    """Count procurement tables on PostgreSQL and the SQLite test backend."""
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                  AND table_name LIKE 'procurement_%'
                ORDER BY table_name
                """
            )
            table_names = [row[0] for row in cursor.fetchall()]
        else:
            table_names = sorted(
                table_name
                for table_name in connection.introspection.table_names(cursor)
                if table_name.startswith("procurement_")
            )
        for table_name in table_names:
            cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}")
            counts[table_name] = int(cursor.fetchone()[0])
    return counts


def _notice_counts() -> dict[str, int]:
    all_notices = ProcurementNotice.objects.all()
    active = all_notices.filter(soft_deleted_at__isnull=True)
    now = timezone.now()
    return {
        "total": all_notices.count(),
        "tenders": active.filter(resolved_notice_type=ProcurementNotice.NoticeType.TENDER).count(),
        "inquiries": active.filter(resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY).count(),
        "expired": active.filter(submission_deadline__lt=now).count(),
        "hidden": active.filter(is_hidden=True).count(),
        "soft_deleted": all_notices.filter(soft_deleted_at__isnull=False).count(),
        "multi_source": active.annotate(source_count=Count("source_links")).filter(source_count__gt=1).count(),
    }


def export_dataset(dataset_id: str, *, actor: str = "system"):
    dataset = _legacy_export_dataset(dataset_id, actor=actor)
    if dataset.status != dataset.Status.READY:
        return dataset

    table_counts = _procurement_table_counts()
    notice_counts = _notice_counts()
    files = list(dataset.files or [])
    manifest_record = next((item for item in files if item.get("kind") == "manifest"), None)
    if manifest_record:
        manifest_path = Path(str(manifest_record["path"]))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["table_record_counts"] = table_counts
        manifest["notice_counts"] = notice_counts
        manifest["total_procurement_table_rows"] = sum(table_counts.values())
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest_record["size_bytes"] = manifest_path.stat().st_size
        manifest_record["sha256"] = legacy._sha256(manifest_path)

    dataset.files = files
    dataset.hashes = {item["name"]: item["sha256"] for item in files}
    dataset.counts = {
        **(dataset.counts or {}),
        "table_record_counts": table_counts,
        "notice_counts": notice_counts,
        "total_procurement_table_rows": sum(table_counts.values()),
    }
    dataset.save(update_fields=["files", "hashes", "counts", "updated_at"])
    return dataset


def install() -> None:
    legacy._candidate_queryset = _candidate_queryset
    legacy.refresh_run_counters = refresh_run_counters
    legacy.claim_run_items = claim_run_items
    legacy.import_result_records = import_result_records
    legacy.cancel_run = cancel_run
    legacy._write_sql_dump = _write_sql_dump
    legacy.export_dataset = export_dataset


install()
