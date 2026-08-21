from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models_extraction import ExtractionRun
from .serializers_extraction import ExtractionErrorSerializer, ExtractionPageSerializer


ACTIVE_EXTRACTION_STATUSES = [
    ExtractionRun.Status.QUEUED,
    ExtractionRun.Status.RUNNING,
]
COMPLETED_EXTRACTION_STATUSES = [
    ExtractionRun.Status.SUCCEEDED,
    ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
    ExtractionRun.Status.PARTIAL,
]
HEZAREH_CONNECTOR_KEYS = ("hezareh_inquiries", "hezareh_tenders")
HEZAREH_EVIDENCE_LIMIT = 50


def _seconds_since(now, value):
    if value is None:
        return None
    return max(0, int((now - value).total_seconds()))


def _active_run_snapshot(run: ExtractionRun, now) -> dict:
    latest_page = (
        run.pages.select_related("connector")
        .exclude(captured_at__isnull=True)
        .order_by("-captured_at", "-created_at")
        .first()
    )
    latest_item = run.items.order_by("-created_at").first()
    latest_error = run.errors.order_by("-created_at").first()

    activity_candidates = [
        run.created_at,
        run.started_at,
        run.updated_at,
        latest_page.captured_at if latest_page else None,
        latest_item.created_at if latest_item else None,
        latest_error.created_at if latest_error else None,
    ]
    latest_activity_at = max(value for value in activity_candidates if value is not None)
    age_anchor = run.started_at or run.created_at

    latest_page_payload = None
    if latest_page is not None:
        latest_page_payload = {
            "connector_key": latest_page.connector.key,
            "page_number": latest_page.page_number,
            "captured_at": latest_page.captured_at,
            "parse_status": latest_page.parse_status,
            "http_status": latest_page.http_status,
            "error_code": latest_page.error_code,
        }

    return {
        "id": str(run.id),
        "status": run.status,
        "trigger": run.trigger,
        "mode": run.mode,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "updated_at": run.updated_at,
        "connector_keys": list(run.connectors.values_list("key", flat=True)),
        "pages_recorded": run.pages.count(),
        "items_recorded": run.items.count(),
        "errors_recorded": run.errors.count(),
        "latest_activity_at": latest_activity_at,
        "age_seconds": _seconds_since(now, age_anchor),
        "idle_seconds": _seconds_since(now, latest_activity_at),
        "latest_page": latest_page_payload,
    }


def _hezareh_acceptance_evidence(run: ExtractionRun) -> dict:
    pages_queryset = (
        run.pages.select_related("connector")
        .filter(connector__key__in=HEZAREH_CONNECTOR_KEYS)
        .order_by("connector__key", "page_number", "created_at")
    )
    errors_queryset = (
        run.errors.select_related("connector")
        .filter(connector__key__in=HEZAREH_CONNECTOR_KEYS)
        .order_by("connector__key", "page_number", "created_at")
    )
    page_count = pages_queryset.count()
    error_count = errors_queryset.count()
    pages = list(pages_queryset[:HEZAREH_EVIDENCE_LIMIT])
    errors = list(errors_queryset[:HEZAREH_EVIDENCE_LIMIT])
    return {
        "run_id": str(run.id),
        "connector_keys": list(HEZAREH_CONNECTOR_KEYS),
        "page_count": page_count,
        "error_count": error_count,
        "pages": ExtractionPageSerializer(pages, many=True).data,
        "errors": ExtractionErrorSerializer(errors, many=True).data,
        "truncated": page_count > len(pages) or error_count > len(errors),
    }


@api_view(["GET"])
def latest_extraction_run(request):
    now = timezone.now()
    active_runs = list(
        ExtractionRun.objects.filter(status__in=ACTIVE_EXTRACTION_STATUSES)
        .prefetch_related("connectors")
        .order_by("created_at")[:10]
    )
    active_payload = [_active_run_snapshot(run, now) for run in active_runs]

    run = (
        ExtractionRun.objects.filter(status__in=COMPLETED_EXTRACTION_STATUSES)
        .prefetch_related("connectors")
        .order_by("-finished_at", "-created_at")
        .first()
    )
    if run is None:
        return Response(
            {
                "available": False,
                "detail": "استخراج تکمیل شده ای وجود ندارد.",
                "active_run_count": len(active_payload),
                "active_runs": active_payload,
            }
        )

    return Response(
        {
            "available": True,
            "id": str(run.id),
            "status": run.status,
            "finished_at": run.finished_at,
            "records_new": run.records_new,
            "records_updated": run.records_updated,
            "records_failed": run.records_failed,
            "connector_keys": list(run.connectors.values_list("key", flat=True)),
            "active_run_count": len(active_payload),
            "active_runs": active_payload,
            "hezareh_acceptance_evidence": _hezareh_acceptance_evidence(run),
        }
    )
