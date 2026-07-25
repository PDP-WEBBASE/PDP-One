from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone

from procurement.connectors.fetchers import fetcher_for
from procurement.connectors.registry import parser_for
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun, ExtractionRunItem
from procurement.tasks_connector_acceptance import (
    ACTIVE_CONNECTOR_KEYS,
    DISABLED_CONNECTOR_KEYS,
    REQUEST_PATH,
    TERMINAL_STATUSES,
    _build_connector_report,
    _page_cap_for,
    _read_json,
    _report_path,
    _safe_value,
    _save_report,
    recover_stale_extraction_runs,
)


def _compact_connector(item):
    return {
        "key": item.get("key"),
        "tested": item.get("tested"),
        "acceptance": item.get("acceptance"),
        "run_status": item.get("run_status"),
        "pages_processed": item.get("pages_processed", 0),
        "records_seen": item.get("records_seen", 0),
        "records_new": item.get("records_new", 0),
        "records_updated": item.get("records_updated", 0),
        "records_duplicate": item.get("records_duplicate", 0),
        "cross_source_duplicate_links": item.get("cross_source_duplicate_links", 0),
        "records_failed": item.get("records_failed", 0),
        "normalized_record_count": item.get("normalized_record_count", 0),
        "error_count": item.get("error_count", 0),
        "raw_samples": item.get("raw_samples", []),
        "normalized_samples": item.get("normalized_samples", []),
        "pages": item.get("pages", []),
        "detail_probes": item.get("detail_probes", []),
        "errors": item.get("errors", [])[:10],
        "errors_truncated": max(0, int(item.get("error_count", 0)) - 10),
        "reason": item.get("reason", ""),
    }


def load_latest_connector_acceptance_report_v2(*, compact=False):
    from procurement.tasks_connector_acceptance import LATEST_PATH

    pointer = _read_json(LATEST_PATH)
    if not pointer:
        return None
    report = _read_json(_report_path(pointer.get("acceptance_id", "")))
    if not report:
        return pointer
    if not compact:
        return report
    return {
        "acceptance_id": report.get("acceptance_id"),
        "schema": report.get("schema"),
        "status": report.get("status"),
        "phase": report.get("phase"),
        "current_connector": report.get("current_connector"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "updated_at": report.get("updated_at"),
        "lookback_days": report.get("lookback_days"),
        "stale_runs_closed": report.get("stale_runs_closed", []),
        "connectors": [_compact_connector(item) for item in report.get("connectors", [])],
        "totals": report.get("totals", {}),
        "report_path": report.get("report_path"),
    }


def _detail_probe(run, connector, *, limit=2):
    if connector.key.startswith("setad_") or not connector.supports_detail:
        return []
    items = list(
        ExtractionRunItem.objects.filter(
            run=run,
            connector=connector,
            source_notice__detail_url__gt="",
        )
        .select_related("source_notice")
        .order_by("page_number", "position")[:limit]
    )
    if not items:
        return []

    allowed_host = urlparse(connector.source.base_url).hostname or ""
    parser = parser_for(connector.key, connector.source.base_url, connector.notice_type)
    fetcher = fetcher_for(connector, allowed_host=allowed_host)
    probes = []
    for item in items:
        source_notice = item.source_notice
        evidence = {
            "source_record_id": source_notice.source_record_id,
            "detail_url": source_notice.detail_url,
            "status": "failed",
        }
        try:
            fetched = fetcher.fetch_detail(source_notice.detail_url)
            parsed = parser.parse_detail(fetched.text)
            detail_status = str(parsed.get("detail_status", "unknown"))
            evidence.update(
                {
                    "http_status": fetched.status_code,
                    "response_bytes": len(fetched.content),
                    "detail_status": detail_status,
                    "status": "passed" if detail_status == "enriched" else "warning",
                    "parsed_detail": _safe_value(parsed),
                }
            )
        except Exception as exc:
            evidence.update(
                {
                    "status": "failed",
                    "safe_error": exc.__class__.__name__,
                }
            )
        probes.append(evidence)
    return probes


def _disabled_report():
    return {
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
        "cross_source_duplicate_links": 0,
        "records_failed": 0,
        "normalized_record_count": 0,
        "error_count": 0,
        "pages": [],
        "raw_samples": [],
        "normalized_samples": [],
        "detail_probes": [],
        "errors": [],
    }


def _blocked_report(connector):
    return {
        "key": connector.key,
        "source": connector.source.key,
        "notice_type": connector.notice_type,
        "tested": False,
        "enabled": connector.enabled,
        "acceptance": "blocked",
        "run_status": "not_run",
        "reason": "A non-stale extraction run is still active for this connector.",
        "pages_processed": 0,
        "records_seen": 0,
        "records_new": 0,
        "records_updated": 0,
        "records_duplicate": 0,
        "cross_source_duplicate_links": 0,
        "records_failed": 0,
        "normalized_record_count": 0,
        "error_count": 0,
        "pages": [],
        "raw_samples": [],
        "normalized_samples": [],
        "detail_probes": [],
        "errors": [],
    }


def _totals(connectors):
    tested = [item for item in connectors if item.get("tested")]
    return {
        "tested_connectors": len(tested),
        "passed": sum(item.get("acceptance") == "passed" for item in tested),
        "warnings": sum(item.get("acceptance") == "warning" for item in tested),
        "failed": sum(item.get("acceptance") == "failed" for item in tested),
        "blocked": sum(item.get("acceptance") == "blocked" for item in connectors),
        "disabled": sum(item.get("acceptance") == "disabled" for item in connectors),
        "pages_processed": sum(int(item.get("pages_processed", 0)) for item in tested),
        "records_seen": sum(int(item.get("records_seen", 0)) for item in tested),
        "records_new": sum(int(item.get("records_new", 0)) for item in tested),
        "records_updated": sum(int(item.get("records_updated", 0)) for item in tested),
        "records_duplicate": sum(int(item.get("records_duplicate", 0)) for item in tested),
        "cross_source_duplicate_links": sum(
            int(item.get("cross_source_duplicate_links", 0)) for item in tested
        ),
        "records_failed": sum(int(item.get("records_failed", 0)) for item in tested),
        "errors": sum(int(item.get("error_count", 0)) for item in tested),
        "detail_probes": sum(len(item.get("detail_probes", [])) for item in tested),
        "detail_probe_passed": sum(
            sum(probe.get("status") == "passed" for probe in item.get("detail_probes", []))
            for item in tested
        ),
    }


@shared_task(name="procurement.run_connector_acceptance_v2")
def run_connector_acceptance_v2(acceptance_id: str, request_payload: dict):
    report = _read_json(_report_path(acceptance_id)) or {
        "schema": "pdp-one.connector-acceptance.v2",
        "acceptance_id": acceptance_id,
        "connectors": [],
    }
    report.update(
        {
            "status": "running",
            "phase": "preparing",
            "current_connector": None,
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
        report["connectors"] = [_disabled_report()]
        _save_report(report)

        from procurement.tasks import run_extraction

        for connector_key in ACTIVE_CONNECTOR_KEYS:
            connector = connectors[connector_key]
            source = sources[connector.source.key]
            report["phase"] = "list_extraction"
            report["current_connector"] = connector_key
            _save_report(report)

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
                report["connectors"].append(_blocked_report(connector))
                _save_report(report)
                continue

            run = ExtractionRun.objects.create(
                trigger=ExtractionRun.Trigger.MANUAL,
                mode=ExtractionRun.Mode.MANUAL_RANGE,
                lookback_days=report["lookback_days"],
                status=ExtractionRun.Status.QUEUED,
                include_details=False,
                analyze_after_success=False,
                page_cap=_page_cap_for(request_payload, connector_key),
                summary={
                    "real_connector_acceptance": True,
                    "acceptance_version": 2,
                    "acceptance_id": acceptance_id,
                    "connector_key": connector_key,
                    "detail_policy": "list-first-then-two-controlled-probes",
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
            connector_report = _build_connector_report(run, connector)
            report["phase"] = "detail_probe"
            _save_report(report)
            connector_report["detail_probes"] = _detail_probe(run, connector, limit=2)

            if connector_report["acceptance"] == "passed" and any(
                probe.get("status") != "passed" for probe in connector_report["detail_probes"]
            ):
                connector_report["acceptance"] = "warning"
                connector_report["reason"] = (
                    "List extraction and persistence passed; one or more controlled detail probes were unavailable."
                )
            report["connectors"].append(connector_report)
            _save_report(report)

        values = [
            item.get("acceptance")
            for item in report["connectors"]
            if item.get("tested")
        ]
        if not values or all(value == "failed" for value in values):
            report["status"] = "failed"
        elif any(value in {"failed", "blocked"} for value in values):
            report["status"] = "partial"
        elif any(value == "warning" for value in values):
            report["status"] = "succeeded_with_warnings"
        else:
            report["status"] = "succeeded"
        report["phase"] = "completed"
        report["current_connector"] = None
        report["totals"] = _totals(report["connectors"])
        report["finished_at"] = timezone.now().isoformat()
        _save_report(report)
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["phase"] = "failed"
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


@shared_task(name="procurement.dispatch_connector_acceptance_v2")
def dispatch_connector_acceptance_v2():
    recover_stale_extraction_runs()
    request_payload = _read_json(REQUEST_PATH)
    if not request_payload or not request_payload.get("enabled"):
        return {"dispatched": False, "reason": "no_enabled_request"}
    if int(request_payload.get("acceptance_version", 1)) != 2:
        return {"dispatched": False, "reason": "not_a_v2_request"}
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
        "schema": "pdp-one.connector-acceptance.v2",
        "acceptance_id": acceptance_id,
        "status": "queued",
        "phase": "queued",
        "current_connector": None,
        "requested_at": timezone.now().isoformat(),
        "lookback_days": int(request_payload.get("lookback_days", 1)),
        "connectors": [],
        "report_path": str(report_path),
    }
    _save_report(report)
    async_result = run_connector_acceptance_v2.delay(acceptance_id, request_payload)
    report["task_id"] = async_result.id
    _save_report(report)
    return {
        "dispatched": True,
        "acceptance_id": acceptance_id,
        "task_id": async_result.id,
    }
