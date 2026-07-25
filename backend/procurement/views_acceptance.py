import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .models import ProcurementConnector
from .models_extraction import ExtractionRun
from .tasks_acceptance import repair_stale_extraction_runs, run_connector_acceptance

ACCEPTANCE_CONNECTOR_KEYS = (
    "hezareh_tenders",
    "hezareh_inquiries",
    "parsnamad_inquiries",
    "setad_tenders",
    "setad_inquiries",
)
DISABLED_CONNECTOR_KEY = "parsnamad_tenders"
TERMINAL_STATUSES = {
    ExtractionRun.Status.SUCCEEDED,
    ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
    ExtractionRun.Status.PARTIAL,
    ExtractionRun.Status.FAILED,
    ExtractionRun.Status.CANCELLED,
}


def _normalized_notice(source_notice):
    if source_notice is None:
        return None
    try:
        link = source_notice.notice_link
        notice = link.procurement_notice
    except Exception:
        return None
    return {
        "id": str(notice.id),
        "notice_type": notice.resolved_notice_type,
        "title": notice.title,
        "employer": notice.employer_name,
        "province": notice.province,
        "published_date": notice.published_date.isoformat() if notice.published_date else None,
        "submission_deadline": notice.submission_deadline.isoformat() if notice.submission_deadline else None,
        "processing_status": notice.processing_status,
    }


def _run_report(run: ExtractionRun) -> dict:
    connector = run.connectors.select_related("source").first()
    items = list(
        run.items.select_related(
            "source_notice",
            "source_notice__notice_link",
            "source_notice__notice_link__procurement_notice",
        ).order_by("page_number", "position")[:10]
    )
    samples = []
    for item in items:
        source_notice = item.source_notice
        samples.append(
            {
                "item_status": item.status,
                "source_record_id": item.source_record_id,
                "page_number": item.page_number,
                "source_url": source_notice.source_url if source_notice else "",
                "detail_url": source_notice.detail_url if source_notice else "",
                "raw_data": source_notice.raw_payload if source_notice else None,
                "standardized_data": _normalized_notice(source_notice),
                "changed_fields": item.changed_fields,
                "message": item.safe_message,
            }
        )

    pages = [
        {
            "page_number": page.page_number,
            "url": page.url,
            "http_status": page.http_status,
            "response_bytes": page.response_bytes,
            "parse_status": page.parse_status,
            "content_hash": page.content_hash,
            "error_code": page.error_code,
            "error_message": page.error_message,
        }
        for page in run.pages.select_related("connector").order_by("page_number")
    ]
    errors = [
        {
            "category": error.category,
            "page_number": error.page_number,
            "url": error.url,
            "message": error.safe_message,
            "retryable": error.retryable,
            "technical_details": error.technical_details,
        }
        for error in run.errors.select_related("connector").order_by("created_at")
    ]

    terminal = run.status in TERMINAL_STATUSES
    has_source_links = bool(samples) and all(sample["source_url"] for sample in samples)
    has_raw_data = any(bool(sample["raw_data"]) for sample in samples)
    has_standardized_data = any(bool(sample["standardized_data"]) for sample in samples)
    if not terminal:
        acceptance = "pending"
    elif run.status in {ExtractionRun.Status.SUCCEEDED, ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS} and run.pages_processed > 0 and run.records_seen > 0 and has_source_links and has_raw_data and has_standardized_data:
        acceptance = "passed"
    elif run.status == ExtractionRun.Status.PARTIAL:
        acceptance = "needs_attention"
    else:
        acceptance = "failed"

    connector_summary = (run.summary or {}).get("connectors", {}).get(connector.key if connector else "", {})
    return {
        "run_id": str(run.id),
        "connector_key": connector.key if connector else "",
        "source": connector.source.name if connector else "",
        "notice_type": connector.notice_type if connector else "",
        "run_status": run.status,
        "acceptance_status": acceptance,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "counts": {
            "pages": run.pages_processed,
            "records_seen": run.records_seen,
            "new": run.records_new,
            "updated": run.records_updated,
            "duplicates": run.records_duplicate,
            "failed": run.records_failed,
            "errors": len(errors),
        },
        "connector_summary": connector_summary,
        "evidence": {
            "source_links_present": has_source_links,
            "raw_data_present": has_raw_data,
            "standardized_data_present": has_standardized_data,
            "sample_count": len(samples),
        },
        "pages": pages,
        "sample_records": samples,
        "errors": errors,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_connector_acceptance(request):
    page_cap = max(2, min(int(request.data.get("page_cap", 3)), 5))
    lookback_days = max(1, min(int(request.data.get("lookback_days", 7)), 30))
    stale_result = repair_stale_extraction_runs(max_age_minutes=30)
    now = timezone.now()

    disabled = ProcurementConnector.objects.select_related("source").filter(key=DISABLED_CONNECTOR_KEY).first()
    disabled_result = {"connector_key": DISABLED_CONNECTOR_KEY, "status": "not_found"}
    if disabled is not None:
        changed = disabled.enabled or disabled.status != ProcurementConnector.Status.INACTIVE
        if changed:
            disabled.enabled = False
            disabled.status = ProcurementConnector.Status.INACTIVE
            disabled.save(update_fields=["enabled", "status", "updated_at"])
        disabled_result = {
            "connector_key": DISABLED_CONNECTOR_KEY,
            "status": "disabled_as_required",
            "changed": changed,
        }

    active_acceptance = (
        ExtractionRun.objects.filter(
            status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING],
            summary__acceptance__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )
    if active_acceptance is not None:
        return Response(
            {
                "started": False,
                "reason": "acceptance_test_already_running",
                "suite_id": (active_acceptance.summary or {}).get("acceptance", {}).get("suite_id"),
                "run_id": str(active_acceptance.id),
                "stale_repair": stale_result,
                "disabled_connector": disabled_result,
            },
            status=409,
        )

    suite_id = uuid.uuid4().hex
    created_runs = []
    skipped = []
    with transaction.atomic():
        for key in ACCEPTANCE_CONNECTOR_KEYS:
            connector = ProcurementConnector.objects.select_related("source").filter(key=key).first()
            if connector is None:
                skipped.append({"connector_key": key, "reason": "connector_not_found"})
                continue
            if not connector.enabled or not connector.source.enabled:
                skipped.append({"connector_key": key, "reason": "connector_disabled"})
                continue
            run = ExtractionRun.objects.create(
                trigger=ExtractionRun.Trigger.MANUAL,
                mode=ExtractionRun.Mode.MANUAL_RANGE,
                lookback_days=lookback_days,
                status=ExtractionRun.Status.QUEUED,
                requested_by=request.user,
                include_details=False,
                analyze_after_success=False,
                page_cap=page_cap,
                summary={
                    "acceptance": {
                        "suite_id": suite_id,
                        "connector_key": key,
                        "requested_at": now.isoformat(),
                        "page_cap": page_cap,
                        "lookback_days": lookback_days,
                        "real_source_data": True,
                        "include_details": False,
                    }
                },
            )
            run.connectors.set([connector])
            created_runs.append({"connector_key": key, "run_id": str(run.id)})

        AuditEvent.objects.create(
            actor=getattr(request.user, "username", "mcp") or "mcp",
            action="procurement.connector_acceptance.start",
            target_type="connector_acceptance_suite",
            target_id=suite_id,
            payload={
                "page_cap": page_cap,
                "lookback_days": lookback_days,
                "run_ids": created_runs,
                "skipped": skipped,
                "stale_repair": stale_result,
                "disabled_connector": disabled_result,
            },
        )

    for item in created_runs:
        run_connector_acceptance.delay(item["run_id"])

    return Response(
        {
            "started": True,
            "suite_id": suite_id,
            "runs": created_runs,
            "skipped": skipped,
            "disabled_connector": disabled_result,
            "stale_repair": stale_result,
            "next_step": "Poll the connector acceptance report with this suite_id.",
        },
        status=202,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def connector_acceptance_report(request, suite_id: str):
    runs = list(
        ExtractionRun.objects.filter(summary__acceptance__suite_id=suite_id)
        .prefetch_related("connectors__source", "pages", "errors", "items")
        .order_by("created_at")
    )
    reports = [_run_report(run) for run in runs]
    statuses = [item["acceptance_status"] for item in reports]
    if not reports:
        overall = "not_found"
    elif any(status == "pending" for status in statuses):
        overall = "running"
    elif all(status == "passed" for status in statuses) and len(reports) == len(ACCEPTANCE_CONNECTOR_KEYS):
        overall = "passed"
    elif any(status == "failed" for status in statuses):
        overall = "failed"
    else:
        overall = "needs_attention"

    disabled = ProcurementConnector.objects.filter(key=DISABLED_CONNECTOR_KEY).values("enabled", "status").first()
    return Response(
        {
            "suite_id": suite_id,
            "overall_status": overall,
            "expected_active_connectors": list(ACCEPTANCE_CONNECTOR_KEYS),
            "completed_connectors": len([status for status in statuses if status != "pending"]),
            "total_connectors": len(reports),
            "parsnamad_tenders": {
                "required_status": "disabled",
                "actual": disabled or {"enabled": None, "status": "not_found"},
            },
            "connectors": reports,
            "generated_at": timezone.now().isoformat(),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def repair_stale_connector_runs(request):
    max_age_minutes = max(15, min(int(request.data.get("max_age_minutes", 30)), 24 * 60))
    result = repair_stale_extraction_runs(max_age_minutes=max_age_minutes)
    AuditEvent.objects.create(
        actor=getattr(request.user, "username", "mcp") or "mcp",
        action="procurement.extraction.watchdog.manual",
        target_type="extraction_run",
        target_id="stale-runs",
        payload=result,
    )
    return Response(result)
