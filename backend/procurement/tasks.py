import hashlib
import time
from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone

from procurement.connectors import parser_for
from procurement.http import SourceFetchError, fetch_public_html
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_extraction import (
    ExtractionError,
    ExtractionPage,
    ExtractionRun,
    ExtractionRunItem,
)


def _record_error(run, connector, *, category, message, retryable, url="", page_number=None, details=None):
    return ExtractionError.objects.create(
        run=run,
        connector=connector,
        page_number=page_number,
        url=url,
        category=category,
        safe_message=message,
        technical_details=details or {},
        retryable=retryable,
    )


def _execute_connector(run: ExtractionRun, connector: ProcurementConnector) -> dict:
    source = connector.source
    allowed_host = urlparse(source.base_url).hostname or ""
    parser = parser_for(connector.key, source.base_url, connector.notice_type)
    page_cap = min(run.page_cap or connector.max_pages, connector.max_pages)
    summary = {
        "status": "succeeded",
        "pages": 0,
        "seen": 0,
        "new": 0,
        "updated": 0,
        "duplicate": 0,
        "failed": 0,
        "warnings": 0,
    }

    for page_number in range(1, page_cap + 1):
        page_url = connector.list_url_template.format(page=page_number)
        try:
            fetched = fetch_public_html(
                page_url,
                allowed_host=allowed_host,
                timeout_seconds=connector.timeout_seconds,
                retry_count=connector.retry_count,
            )
        except SourceFetchError as exc:
            ExtractionPage.objects.create(
                run=run,
                connector=connector,
                page_number=page_number,
                url=page_url,
                http_status=exc.status_code,
                parse_status=ExtractionPage.ParseStatus.FAILED,
                captured_at=timezone.now(),
                error_code=exc.category,
                error_message=str(exc),
            )
            _record_error(
                run,
                connector,
                category=exc.category,
                message=str(exc),
                retryable=exc.retryable,
                url=page_url,
                page_number=page_number,
                details={"status_code": exc.status_code},
            )
            summary["failed"] += 1
            summary["status"] = "failed"
            break

        try:
            parsed_page = parser.parse_list(fetched.text, fetched.url)
        except Exception as exc:
            ExtractionPage.objects.create(
                run=run,
                connector=connector,
                page_number=page_number,
                url=fetched.url,
                http_status=fetched.status_code,
                content_hash=hashlib.sha256(fetched.content).hexdigest(),
                response_bytes=len(fetched.content),
                parse_status=ExtractionPage.ParseStatus.FAILED,
                captured_at=timezone.now(),
                error_code="parse",
                error_message="ساختار صفحه با Parser فعلی سازگار نبود.",
            )
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.PARSE,
                message="ساختار صفحه با Parser فعلی سازگار نبود.",
                retryable=False,
                url=fetched.url,
                page_number=page_number,
                details={"exception": exc.__class__.__name__},
            )
            summary["failed"] += 1
            summary["status"] = "failed"
            break

        page_status = (
            ExtractionPage.ParseStatus.WARNING
            if parsed_page.warnings
            else ExtractionPage.ParseStatus.SUCCEEDED
        )
        ExtractionPage.objects.create(
            run=run,
            connector=connector,
            page_number=page_number,
            url=fetched.url,
            http_status=fetched.status_code,
            content_hash=hashlib.sha256(fetched.content).hexdigest(),
            response_bytes=len(fetched.content),
            parse_status=page_status,
            captured_at=timezone.now(),
            error_message=" | ".join(parsed_page.warnings)[:1000],
        )
        summary["pages"] += 1
        summary["seen"] += len(parsed_page.notices)
        summary["warnings"] += len(parsed_page.warnings)

        if not parsed_page.notices:
            break

        for parsed in parsed_page.notices:
            detail = None
            if run.include_details and connector.supports_detail and parsed.detail_url:
                try:
                    detail_page = fetch_public_html(
                        parsed.detail_url,
                        allowed_host=allowed_host,
                        timeout_seconds=connector.timeout_seconds,
                        retry_count=connector.retry_count,
                    )
                    detail = parser.parse_detail(detail_page.text)
                    if detail.get("detail_status") == "security_challenge":
                        summary["warnings"] += 1
                    delay_ms = int(source.configuration.get("detail_delay_ms", 250))
                    if delay_ms > 0:
                        time.sleep(min(delay_ms, 2000) / 1000)
                except SourceFetchError as exc:
                    detail = {"detail_status": "failed"}
                    summary["warnings"] += 1
                    _record_error(
                        run,
                        connector,
                        category=exc.category,
                        message="صفحه جزئیات دریافت نشد؛ اطلاعات فهرست ذخیره می‌شود.",
                        retryable=exc.retryable,
                        url=parsed.detail_url,
                        page_number=page_number,
                        details={"status_code": exc.status_code, "exception": exc.__class__.__name__},
                    )
                except Exception as exc:
                    detail = {"detail_status": "failed"}
                    summary["warnings"] += 1
                    _record_error(
                        run,
                        connector,
                        category=ExtractionError.Category.PARSE,
                        message="صفحه جزئیات پردازش نشد؛ اطلاعات فهرست ذخیره می‌شود.",
                        retryable=False,
                        url=parsed.detail_url,
                        page_number=page_number,
                        details={"exception": exc.__class__.__name__},
                    )

            try:
                _, _, item_status = ingest_parsed_notice(
                    connector,
                    parsed,
                    detail=detail,
                    run=run,
                    page_number=page_number,
                )
                summary[item_status] += 1
            except Exception as exc:
                summary["failed"] += 1
                ExtractionRunItem.objects.create(
                    run=run,
                    connector=connector,
                    source_record_id=parsed.source_record_id,
                    page_number=page_number,
                    position=parsed.position,
                    status=ExtractionRunItem.Status.FAILED,
                    safe_message="رکورد دریافت شد اما ذخیره‌سازی آن ناموفق بود.",
                )
                _record_error(
                    run,
                    connector,
                    category=ExtractionError.Category.UNEXPECTED,
                    message="رکورد دریافت شد اما ذخیره‌سازی آن ناموفق بود.",
                    retryable=True,
                    url=parsed.detail_url or page_url,
                    page_number=page_number,
                    details={"exception": exc.__class__.__name__, "source_record_id": parsed.source_record_id},
                )

        connector.last_successful_page = page_number
        connector.save(update_fields=["last_successful_page", "updated_at"])

    if summary["status"] == "succeeded" and summary["warnings"]:
        summary["status"] = "succeeded_with_warnings"
    return summary


@shared_task(name="procurement.run_extraction")
def run_extraction(run_id: str) -> dict:
    run = ExtractionRun.objects.prefetch_related("connectors__source").get(pk=run_id)
    run.status = ExtractionRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])

    summaries = {}
    connectors = list(run.connectors.select_related("source").all())
    runnable = [connector for connector in connectors if connector.enabled and connector.source.enabled]
    skipped = [connector.key for connector in connectors if connector not in runnable]

    for connector in runnable:
        summary = _execute_connector(run, connector)
        summaries[connector.key] = summary
        now = timezone.now()
        if summary["status"] == "failed":
            connector.status = ProcurementConnector.Status.ERROR
            connector.last_failure_at = now
            connector.save(update_fields=["status", "last_failure_at", "updated_at"])
        else:
            connector.status = ProcurementConnector.Status.ACTIVE
            connector.last_success_at = now
            connector.save(update_fields=["status", "last_success_at", "updated_at"])

    failed_connectors = [key for key, value in summaries.items() if value["status"] == "failed"]
    warning_connectors = [key for key, value in summaries.items() if value["status"] == "succeeded_with_warnings"]
    if not runnable:
        run.status = ExtractionRun.Status.CANCELLED
    elif len(failed_connectors) == len(runnable):
        run.status = ExtractionRun.Status.FAILED
    elif failed_connectors:
        run.status = ExtractionRun.Status.PARTIAL
    elif warning_connectors or skipped:
        run.status = ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS
    else:
        run.status = ExtractionRun.Status.SUCCEEDED

    totals = {
        field: sum(summary[field] for summary in summaries.values())
        for field in ("pages", "seen", "new", "updated", "duplicate", "failed")
    }
    run.pages_processed = totals["pages"]
    run.records_seen = totals["seen"]
    run.records_new = totals["new"]
    run.records_updated = totals["updated"]
    run.records_duplicate = totals["duplicate"]
    run.records_failed = totals["failed"]
    run.summary = {"connectors": summaries, "skipped_disabled_connectors": skipped}
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "pages_processed",
            "records_seen",
            "records_new",
            "records_updated",
            "records_duplicate",
            "records_failed",
            "summary",
            "finished_at",
            "updated_at",
        ]
    )

    for source in ProcurementSource.objects.filter(connectors__in=runnable).distinct():
        source_summaries = [summaries[c.key] for c in runnable if c.source_id == source.id]
        now = timezone.now()
        if any(item["status"] == "failed" for item in source_summaries):
            source.status = ProcurementSource.Status.DEGRADED
            source.last_failure_at = now
            source.save(update_fields=["status", "last_failure_at", "updated_at"])
        else:
            source.status = ProcurementSource.Status.ACTIVE
            source.last_success_at = now
            source.save(update_fields=["status", "last_success_at", "updated_at"])

    return {"run_id": str(run.id), "status": run.status, "summary": run.summary}
