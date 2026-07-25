import json
import os
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from procurement.models import NoticeSourceLink, ProcurementConnector, ProcurementSource
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun, ExtractionRunItem


REQUEST_PATH = Path(__file__).with_name("connector_acceptance_request.json")
REPORT_ROOT = Path(settings.MEDIA_ROOT) / "connector-acceptance"
LATEST_PATH = REPORT_ROOT / "latest.json"
TERMINAL_STATUSES = {"succeeded", "succeeded_with_warnings", "partial", "failed"}
ACTIVE_CONNECTOR_KEYS = [
    "hezareh_tenders",
    "hezareh_inquiries",
    "parsnamad_inquiries",
    "setad_tenders",
    "setad_inquiries",
]
DISABLED_CONNECTOR_KEYS = ["parsnamad_tenders"]


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_value(value, *, depth=0):
    if depth > 5:
        return "[depth-limited]"
    if isinstance(value, dict):
        output = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 60:
                output["__truncated__"] = True
                break
            output[str(key)[:200]] = _safe_value(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        values = list(value)
        output = [_safe_value(item, depth=depth + 1) for item in values[:30]]
        if len(values) > 30:
            output.append("[list-truncated]")
        return output
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "...[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:4000]


def _atomic_write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _report_path(acceptance_id: str) -> Path:
    safe_id = "".join(character for character in acceptance_id if character.isalnum() or character in "._-")
    if safe_id != acceptance_id or not safe_id:
        raise ValueError("Invalid connector acceptance identifier.")
    return REPORT_ROOT / f"{safe_id}.json"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_report(report: dict):
    report["updated_at"] = timezone.now().isoformat()
    path = _report_path(report["acceptance_id"])
    _atomic_write(path, report)
    _atomic_write(
        LATEST_PATH,
        {
            "acceptance_id": report["acceptance_id"],
            "status": report.get("status"),
            "updated_at": report.get("updated_at"),
            "report_path": str(path),
        },
    )


def load_latest_connector_acceptance_report(*, compact=False):
    pointer = _read_json(LATEST_PATH)
    if not pointer:
        return None
    report = _read_json(_report_path(pointer.get("acceptance_id", "")))
    if not report:
        return pointer
    if not compact:
        return report
    connectors = []
    for item in report.get("connectors", []):
        connectors.append(
            {
                "key": item.get("key"),
                "tested": item.get("tested"),
                "acceptance": item.get("acceptance"),
                "run_status": item.get("run_status"),
                "pages_processed": item.get("pages_processed", 0),
                "records_seen": item.get("records_seen", 0),
                "records_new": item.get("records_new", 0),
                "records_updated": item.get("records_updated", 0),
                "records_duplicate": item.get("records_duplicate", 0),
                "records_failed": item.get("records_failed", 0),
                "error_count": item.get("error_count", 0),
                "raw_samples": item.get("raw_samples", []),
                "normalized_samples": item.get("normalized_samples", []),
                "pages": item.get("pages", []),
                "errors": item.get("errors", []),
                "reason": item.get("reason", ""),
            }
        )
    return {
        "acceptance_id": report.get("acceptance_id"),
        "status": report.get("status"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "updated_at": report.get("updated_at"),
        "lookback_days": report.get("lookback_days"),
        "stale_runs_closed": report.get("stale_runs_closed", []),
        "connectors": connectors,
        "totals": report.get("totals", {}),
        "report_path": report.get("report_path"),
    }


def recover_stale_extraction_runs(*, now=None, queued_minutes=30, running_hours=2):
    now = now or timezone.now()
    queued_cutoff = now - timedelta(minutes=queued_minutes)
    running_cutoff = now - timedelta(hours=running_hours)
    stale_runs = list(
        ExtractionRun.objects.filter(
            Q(status=ExtractionRun.Status.QUEUED, created_at__lt=queued_cutoff)
            | Q(status=ExtractionRun.Status.RUNNING, started_at__lt=running_cutoff)
        ).prefetch_related("connectors")
    )
    closed = []
    for run in stale_runs:
        previous_status = run.status
        summary = dict(run.summary or {})
        summary["stale_worker_run"] = {
            "closed_at": now.isoformat(),
            "previous_status": previous_status,
            "reason": "Run exceeded the guarded queued/running age and no longer represented active work.",
        }
        run.status = ExtractionRun.Status.CANCELLED
        run.finished_at = now
        run.summary = summary
        run.save(update_fields=["status", "finished_at", "summary", "updated_at"])
        closed.append(
            {
                "run_id": str(run.id),
                "previous_status": previous_status,
                "connector_keys": list(run.connectors.values_list("key", flat=True)),
                "created_at": run.created_at.isoformat(),
                "started_at": run.started_at.isoformat() if run.started_at else None,
            }
        )
    return closed


def _page_cap_for(request_payload: dict, connector_key: str) -> int:
    configured = request_payload.get("page_caps") or {}
    default = 3 if connector_key.startswith("setad_") else 5
    value = int(configured.get(connector_key, default))
    return max(1, min(value, 10 if not connector_key.startswith("setad_") else 5))


def _sample_payloads(run: ExtractionRun, connector: ProcurementConnector, limit=2):
    items = list(
        ExtractionRunItem.objects.filter(run=run, connector=connector, source_notice__isnull=False)
        .select_related("source_notice")
        .order_by("page_number", "position")[: max(limit * 4, 8)]
    )
    raw_samples = []
    normalized_samples = []
    seen_source_ids = set()
    seen_notice_ids = set()
    cross_source_duplicate_links = 0

    for item in items:
        source_notice = item.source_notice
        if source_notice.id not in seen_source_ids and len(raw_samples) < limit:
            seen_source_ids.add(source_notice.id)
            raw_samples.append(
                {
                    "source_record_id": source_notice.source_record_id,
                    "source_url": source_notice.source_url,
                    "detail_url": source_notice.detail_url,
                    "title_raw": source_notice.title_raw,
                    "employer_raw": source_notice.employer_raw,
                    "published_at_raw": source_notice.published_at_raw,
                    "deadline_raw": source_notice.deadline_raw,
                    "raw_payload": _safe_value(source_notice.raw_payload),
                }
            )

        source_link = (
            NoticeSourceLink.objects.filter(source_notice=source_notice)
            .select_related("procurement_notice")
            .first()
        )
        if source_link is None:
            continue
        notice = source_link.procurement_notice
        if notice.id in seen_notice_ids:
            continue
        seen_notice_ids.add(notice.id)
        linked_sources = notice.source_links.count()
        if linked_sources > 1:
            cross_source_duplicate_links += 1
        if len(normalized_samples) < limit:
            normalized_samples.append(
                {
                    "notice_id": str(notice.id),
                    "resolved_notice_type": notice.resolved_notice_type,
                    "type_resolution_status": notice.type_resolution_status,
                    "title": notice.title,
                    "employer_name": notice.employer_name,
                    "notice_number": notice.notice_number,
                    "province": notice.province,
                    "published_date": notice.published_date.isoformat() if notice.published_date else None,
                    "submission_deadline": notice.submission_deadline.isoformat() if notice.submission_deadline else None,
                    "processing_status": notice.processing_status,
                    "linked_source_count": linked_sources,
                }
            )

    return raw_samples, normalized_samples, cross_source_duplicate_links


def _build_connector_report(run: ExtractionRun, connector: ProcurementConnector):
    pages = list(
        run.pages.filter(connector=connector)
        .order_by("page_number")
        .values(
            "page_number",
            "url",
            "http_status",
            "response_bytes",
            "parse_status",
            "error_code",
            "error_message",
            "captured_at",
        )
    )
    errors = list(
        run.errors.filter(connector=connector)
        .order_by("created_at")
        .values(
            "category",
            "safe_message",
            "retryable",
            "page_number",
            "url",
            "created_at",
        )
    )
    item_counts = {
        status: run.items.filter(connector=connector, status=status).count()
        for status in (
            ExtractionRunItem.Status.NEW,
            ExtractionRunItem.Status.UPDATED,
            ExtractionRunItem.Status.DUPLICATE,
            ExtractionRunItem.Status.SKIPPED,
            ExtractionRunItem.Status.FAILED,
        )
    }
    raw_samples, normalized_samples, cross_source_duplicate_links = _sample_payloads(run, connector)
    connector_summary = (run.summary.get("connectors") or {}).get(connector.key, {})
    pages_processed = len(pages)
    records_seen = sum(item_counts.values()) - item_counts[ExtractionRunItem.Status.SKIPPED]
    normalized_count = run.items.filter(
        connector=connector,
        source_notice__notice_link__procurement_notice__isnull=False,
    ).values("source_notice__notice_link__procurement_notice").distinct().count()

    acceptance = "passed"
    reason = "Real source pages were fetched, parsed, persisted as raw records, and linked to normalized notices."
    if run.status in {ExtractionRun.Status.FAILED, ExtractionRun.Status.PARTIAL}:
        acceptance = "failed"
        reason = "The connector run failed or was partial; inspect page and error details."
    elif pages_processed == 0:
        acceptance = "failed"
        reason = "No source page was persisted."
    elif records_seen == 0:
        acceptance = "warning"
        reason = "Pages were reached but no record was available in the controlled date/page window."
    elif not raw_samples or not normalized_samples:
        acceptance = "failed"
        reason = "Raw or normalized evidence was not available for records touched by the run."
    elif errors or run.status == ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS:
        acceptance = "warning"
        reason = "The connector produced real data but also recorded warnings or recoverable errors."

    return {
        "key": connector.key,
        "source": connector.source.key,
        "notice_type": connector.notice_type,
        "tested": True,
        "enabled": connector.enabled,
        "connector_status": connector.status,
        "parser_version": connector.parser_version,
        "run_id": str(run.id),
        "run_status": run.status,
        "acceptance": acceptance,
        "reason": reason,
        "page_cap": run.page_cap,
        "pages_processed": pages_processed,
        "records_seen": records_seen,
        "records_new": item_counts[ExtractionRunItem.Status.NEW],
        "records_updated": item_counts[ExtractionRunItem.Status.UPDATED],
        "records_duplicate": item_counts[ExtractionRunItem.Status.DUPLICATE],
        "records_skipped": item_counts[ExtractionRunItem.Status.SKIPPED],
        "records_failed": item_counts[ExtractionRunItem.Status.FAILED],
        "normalized_record_count": normalized_count,
        "cross_source_duplicate_links": cross_source_duplicate_links,
        "source_links_present": all(sample.get("source_url") for sample in raw_samples),
        "raw_payload_present": all(sample.get("raw_payload") is not None for sample in raw_samples),
        "pages": [_safe_value(page) for page in pages],
        "raw_samples": raw_samples,
        "normalized_samples": normalized_samples,
        "error_count": len(errors),
        "errors": [_safe_value(error) for error in errors],
        "connector_summary": _safe_value(connector_summary),
    }


@shared_task(name="procurement.run_connector_acceptance")
def run_connector_acceptance(acceptance_id: str, request_payload: dict):
    report = _read_json(_report_path(acceptance_id)) or {
        "schema": "pdp-one.connector-acceptance.v1",
        "acceptance_id": acceptance_id,
        "connectors": [],
    }
    report.update(
        {
            "status": "running",
            "started_at": report.get("started_at") or timezone.now().isoformat(),
            "finished_at": None,
            "lookback_days": int(request_payload.get("lookback_days", 1)),
            "report_path": str(_report_path(acceptance_id)),
        }
    )
    _save_report(report)

    automation = ProcurementAutomationSettings.objects.filter(key="default").first()
    automation_was_enabled = bool(automation and automation.enabled)
    if automation_was_enabled:
        automation.enabled = False
        automation.save(update_fields=["enabled", "updated_at"])

    try:
        report["stale_runs_closed"] = recover_stale_extraction_runs()
        _save_report(report)

        sources = {
            source.key: source
            for source in ProcurementSource.objects.filter(key__in=["hezareh", "parsnamad", "setad"])
        }
        connectors = {
            connector.key: connector
            for connector in ProcurementConnector.objects.filter(
                key__in=ACTIVE_CONNECTOR_KEYS + DISABLED_CONNECTOR_KEYS
            ).select_related("source")
        }

        missing = [key for key in ACTIVE_CONNECTOR_KEYS + DISABLED_CONNECTOR_KEYS if key not in connectors]
        if missing:
            raise RuntimeError("Missing configured connectors: " + ", ".join(missing))

        parsnamad_tenders = connectors["parsnamad_tenders"]
        parsnamad_tenders.enabled = False
        parsnamad_tenders.status = ProcurementConnector.Status.INACTIVE
        parsnamad_tenders.save(update_fields=["enabled", "status", "updated_at"])

        report["connectors"] = [
            {
                "key": "parsnamad_tenders",
                "source": "parsnamad",
                "notice_type": "tender",
                "tested": False,
                "enabled": False,
                "acceptance": "disabled",
                "run_status": "not_run",
                "reason": "Disabled by the approved product decision because the source currently exposes inquiry content on the tender route.",
                "pages_processed": 0,
                "records_seen": 0,
                "records_new": 0,
                "records_updated": 0,
                "records_duplicate": 0,
                "records_failed": 0,
                "error_count": 0,
                "pages": [],
                "raw_samples": [],
                "normalized_samples": [],
                "errors": [],
            }
        ]
        _save_report(report)

        from procurement.tasks import run_extraction

        for connector_key in ACTIVE_CONNECTOR_KEYS:
            connector = connectors[connector_key]
            source = sources.get(connector.source.key)
            if source is None:
                raise RuntimeError(f"Source is missing for connector {connector_key}.")
            source.enabled = True
            source.status = ProcurementSource.Status.ACTIVE
            source.save(update_fields=["enabled", "status", "updated_at"])
            connector.enabled = True
            connector.status = ProcurementConnector.Status.ACTIVE
            connector.save(update_fields=["enabled", "status", "updated_at"])

            active_conflict = ExtractionRun.objects.filter(
                status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING],
                connectors=connector,
            ).exists()
            if active_conflict:
                connector_report = {
                    "key": connector.key,
                    "source": source.key,
                    "notice_type": connector.notice_type,
                    "tested": False,
                    "enabled": True,
                    "acceptance": "blocked",
                    "run_status": "not_run",
                    "reason": "A non-stale extraction run is still active for this connector.",
                    "pages_processed": 0,
                    "records_seen": 0,
                    "records_new": 0,
                    "records_updated": 0,
                    "records_duplicate": 0,
                    "records_failed": 0,
                    "error_count": 0,
                    "pages": [],
                    "raw_samples": [],
                    "normalized_samples": [],
                    "errors": [],
                }
                report["connectors"].append(connector_report)
                _save_report(report)
                continue

            include_details = not connector_key.startswith("setad_")
            run = ExtractionRun.objects.create(
                trigger=ExtractionRun.Trigger.MANUAL,
                mode=ExtractionRun.Mode.MANUAL_RANGE,
                lookback_days=report["lookback_days"],
                status=ExtractionRun.Status.QUEUED,
                include_details=include_details,
                analyze_after_success=False,
                page_cap=_page_cap_for(request_payload, connector_key),
                summary={
                    "real_connector_acceptance": True,
                    "acceptance_id": acceptance_id,
                    "connector_key": connector_key,
                    "detail_policy": "list-and-detail" if include_details else "public-list-only-no-captcha-bypass",
                },
            )
            run.connectors.add(connector)
            try:
                run_extraction(str(run.id))
            except Exception as exc:
                run.refresh_from_db()
                summary = dict(run.summary or {})
                summary["acceptance_task_exception"] = exc.__class__.__name__
                if run.status in {ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING}:
                    run.status = ExtractionRun.Status.FAILED
                    run.finished_at = timezone.now()
                run.summary = summary
                run.save(update_fields=["status", "finished_at", "summary", "updated_at"])
            run.refresh_from_db()
            report["connectors"].append(_build_connector_report(run, connector))
            _save_report(report)

        tested_reports = [item for item in report["connectors"] if item.get("tested")]
        acceptance_values = [item.get("acceptance") for item in tested_reports]
        if not tested_reports or all(value == "failed" for value in acceptance_values):
            report["status"] = "failed"
        elif any(value in {"failed", "blocked"} for value in acceptance_values):
            report["status"] = "partial"
        elif any(value == "warning" for value in acceptance_values):
            report["status"] = "succeeded_with_warnings"
        else:
            report["status"] = "succeeded"

        report["totals"] = {
            "tested_connectors": len(tested_reports),
            "passed": sum(item.get("acceptance") == "passed" for item in tested_reports),
            "warnings": sum(item.get("acceptance") == "warning" for item in tested_reports),
            "failed": sum(item.get("acceptance") == "failed" for item in tested_reports),
            "blocked": sum(item.get("acceptance") == "blocked" for item in tested_reports),
            "disabled": sum(item.get("acceptance") == "disabled" for item in report["connectors"]),
            "pages_processed": sum(int(item.get("pages_processed", 0)) for item in tested_reports),
            "records_seen": sum(int(item.get("records_seen", 0)) for item in tested_reports),
            "records_new": sum(int(item.get("records_new", 0)) for item in tested_reports),
            "records_updated": sum(int(item.get("records_updated", 0)) for item in tested_reports),
            "records_duplicate": sum(int(item.get("records_duplicate", 0)) for item in tested_reports),
            "records_failed": sum(int(item.get("records_failed", 0)) for item in tested_reports),
            "errors": sum(int(item.get("error_count", 0)) for item in tested_reports),
        }
        report["finished_at"] = timezone.now().isoformat()
        _save_report(report)
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["fatal_error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc)[:1000],
        }
        report["finished_at"] = timezone.now().isoformat()
        _save_report(report)
        raise
    finally:
        if automation is not None and automation_was_enabled:
            automation.enabled = True
            automation.save(update_fields=["enabled", "updated_at"])


@shared_task(name="procurement.dispatch_connector_acceptance")
def dispatch_connector_acceptance():
    recover_stale_extraction_runs()
    request_payload = _read_json(REQUEST_PATH)
    if not request_payload or not request_payload.get("enabled"):
        return {"dispatched": False, "reason": "no_enabled_request"}
    acceptance_id = str(request_payload.get("acceptance_id", "")).strip()
    if not acceptance_id:
        return {"dispatched": False, "reason": "missing_acceptance_id"}

    report_path = _report_path(acceptance_id)
    report = _read_json(report_path)
    if report and report.get("status") in TERMINAL_STATUSES:
        return {
            "dispatched": False,
            "reason": "already_completed",
            "acceptance_id": acceptance_id,
            "status": report.get("status"),
        }
    if report and report.get("status") in {"queued", "running"}:
        return {
            "dispatched": False,
            "reason": "already_in_progress",
            "acceptance_id": acceptance_id,
            "status": report.get("status"),
        }

    report = {
        "schema": "pdp-one.connector-acceptance.v1",
        "acceptance_id": acceptance_id,
        "status": "queued",
        "requested_at": timezone.now().isoformat(),
        "lookback_days": int(request_payload.get("lookback_days", 1)),
        "connectors": [],
        "report_path": str(report_path),
    }
    _save_report(report)
    async_result = run_connector_acceptance.delay(acceptance_id, request_payload)
    report["task_id"] = async_result.id
    _save_report(report)
    return {
        "dispatched": True,
        "acceptance_id": acceptance_id,
        "task_id": async_result.id,
    }
