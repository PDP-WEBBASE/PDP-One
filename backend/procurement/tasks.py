import hashlib
import time
from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone

from procurement.connectors import parser_for
from procurement.connectors.fetchers import fetcher_for
from procurement.http import SourceFetchError
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


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _content_retry_settings(source: ProcurementSource) -> tuple[int, int]:
    configuration = source.configuration or {}
    retry_count = _safe_int(configuration.get("content_retry_count"), 2)
    retry_delay_ms = _safe_int(configuration.get("content_retry_delay_ms"), 1200)
    return max(0, min(retry_count, 3)), max(0, min(retry_delay_ms, 5000))


def _fetch_and_parse_with_content_retries(
    *,
    connector: ProcurementConnector,
    allowed_host: str,
    parser,
    fetcher,
    page_number: int,
    page_url: str,
):
    retry_count, retry_delay_ms = _content_retry_settings(connector.source)
    attempts = []
    last_fetch_error = None
    last_parse_error = None

    for attempt in range(1, retry_count + 2):
        try:
            fetched = fetcher.fetch_list(page_number, page_url)
            last_fetch_error = None
        except SourceFetchError as exc:
            last_fetch_error = exc
            attempts.append(
                {
                    "attempt": attempt,
                    "result": "fetch_error",
                    "category": exc.category,
                    "status_code": exc.status_code,
                }
            )
            if attempt > retry_count or not exc.retryable:
                raise
        else:
            try:
                parsed_page = parser.parse_list(fetched.text, fetched.url)
                last_parse_error = None
            except Exception as exc:  # Parser errors are retried with a fresh session.
                last_parse_error = exc
                attempts.append(
                    {
                        "attempt": attempt,
                        "result": "parse_error",
                        "exception": exc.__class__.__name__,
                        "status_code": fetched.status_code,
                        "response_bytes": len(fetched.content),
                        "content_hash": hashlib.sha256(fetched.content).hexdigest(),
                    }
                )
                if attempt > retry_count:
                    raise
            else:
                attempts.append(
                    {
                        "attempt": attempt,
                        "result": "parsed",
                        "status_code": fetched.status_code,
                        "response_bytes": len(fetched.content),
                        "content_hash": hashlib.sha256(fetched.content).hexdigest(),
                        "records": len(parsed_page.notices),
                        "warnings": list(parsed_page.warnings),
                        "reported_current_page": parsed_page.reported_current_page,
                        "reported_total_pages": parsed_page.reported_total_pages,
                        "end_of_results": parsed_page.end_of_results,
                        "diagnostics": dict(parsed_page.diagnostics or {}),
                    }
                )
                if parsed_page.notices or parsed_page.end_of_results is True:
                    return fetched, parsed_page, attempts
                if attempt > retry_count:
                    return fetched, parsed_page, attempts

        if attempt <= retry_count:
            if retry_delay_ms:
                time.sleep(retry_delay_ms / 1000)
            # A new fetcher creates a fresh cookie/session context where the
            # connector implementation supports sessions.
            fetcher = fetcher_for(connector, allowed_host=allowed_host)

    if last_fetch_error is not None:
        raise last_fetch_error
    if last_parse_error is not None:
        raise last_parse_error
    raise RuntimeError("Content retry loop ended without a result.")


def _create_page_record(
    *,
    run,
    connector,
    page_number,
    fetched,
    parsed_page,
    attempts,
    parse_status,
    error_code="",
    error_message="",
):
    return ExtractionPage.objects.create(
        run=run,
        connector=connector,
        page_number=page_number,
        url=fetched.url,
        http_status=fetched.status_code,
        content_hash=hashlib.sha256(fetched.content).hexdigest(),
        response_bytes=len(fetched.content),
        parse_status=parse_status,
        captured_at=timezone.now(),
        error_code=error_code,
        error_message=error_message[:1000],
    )


def _execute_connector(run: ExtractionRun, connector: ProcurementConnector) -> dict:
    source = connector.source
    allowed_host = urlparse(source.base_url).hostname or ""
    parser = parser_for(connector.key, source.base_url, connector.notice_type)
    fetcher = fetcher_for(connector, allowed_host=allowed_host)
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
        "requested_page_cap": page_cap,
        "reported_total_pages": None,
        "last_successful_page": None,
        "stop_reason": "",
        "completeness": "unknown",
        "content_retry_attempts": 0,
        "recovered_pages": [],
        "suspicious_pages": [],
    }
    previous_record_ids: tuple[str, ...] | None = None

    for page_number in range(1, page_cap + 1):
        page_url = connector.list_url_template.format(page=page_number)
        try:
            fetched, parsed_page, attempts = _fetch_and_parse_with_content_retries(
                connector=connector,
                allowed_host=allowed_host,
                parser=parser,
                fetcher=fetcher,
                page_number=page_number,
                page_url=page_url,
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
            summary["completeness"] = "failed"
            summary["stop_reason"] = "fetch_failed"
            break
        except Exception as exc:
            ExtractionPage.objects.create(
                run=run,
                connector=connector,
                page_number=page_number,
                url=page_url,
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
                url=page_url,
                page_number=page_number,
                details={"exception": exc.__class__.__name__},
            )
            summary["failed"] += 1
            summary["status"] = "failed"
            summary["completeness"] = "failed"
            summary["stop_reason"] = "parse_failed"
            break

        retry_attempts = max(0, len(attempts) - 1)
        summary["content_retry_attempts"] += retry_attempts
        if retry_attempts and parsed_page.notices:
            summary["recovered_pages"].append(page_number)
            summary["warnings"] += 1

        if parsed_page.reported_total_pages is not None:
            current_total = summary["reported_total_pages"] or 0
            summary["reported_total_pages"] = max(
                current_total,
                parsed_page.reported_total_pages,
            )

        record_ids = tuple(notice.source_record_id for notice in parsed_page.notices)
        if record_ids and previous_record_ids == record_ids:
            summary["warnings"] += 1
            summary["status"] = "partial"
            summary["completeness"] = "incomplete"
            summary["stop_reason"] = "duplicate_page_content"
            summary["suspicious_pages"].append(page_number)
            _create_page_record(
                run=run,
                connector=connector,
                page_number=page_number,
                fetched=fetched,
                parsed_page=parsed_page,
                attempts=attempts,
                parse_status=ExtractionPage.ParseStatus.WARNING,
                error_code="duplicate_page_content",
                error_message="محتوای این صفحه با صفحه قبلی یکسان بود؛ استخراج ناقص متوقف شد.",
            )
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.VALIDATION,
                message="صفحه تکراری دریافت شد؛ برای جلوگیری از ثبت ناقص یا تکراری استخراج متوقف شد.",
                retryable=True,
                url=fetched.url,
                page_number=page_number,
                details={"attempts": attempts, "record_count": len(record_ids)},
            )
            break

        if not parsed_page.notices:
            natural_end = parsed_page.end_of_results is True
            effective_warnings = list(parsed_page.warnings)
            summary["pages"] += 1
            if natural_end:
                effective_warnings = [
                    warning for warning in effective_warnings if warning != "no_notice_rows_found"
                ]
                summary["warnings"] += len(effective_warnings)
                summary["completeness"] = "complete"
                summary["stop_reason"] = "source_reported_end"
                _create_page_record(
                    run=run,
                    connector=connector,
                    page_number=page_number,
                    fetched=fetched,
                    parsed_page=parsed_page,
                    attempts=attempts,
                    parse_status=(
                        ExtractionPage.ParseStatus.WARNING
                        if effective_warnings
                        else ExtractionPage.ParseStatus.SUCCEEDED
                    ),
                    error_message=" | ".join(effective_warnings),
                )
                break

            summary["warnings"] += max(1, len(effective_warnings))
            summary["status"] = "partial"
            summary["completeness"] = "incomplete"
            summary["stop_reason"] = "unexpected_empty_page"
            summary["suspicious_pages"].append(page_number)
            _create_page_record(
                run=run,
                connector=connector,
                page_number=page_number,
                fetched=fetched,
                parsed_page=parsed_page,
                attempts=attempts,
                parse_status=ExtractionPage.ParseStatus.WARNING,
                error_code="unexpected_empty_page",
                error_message=(
                    "صفحه بدون رکورد بود اما پایان واقعی فهرست تأیید نشد؛ "
                    "استخراج ناقص متوقف شد."
                ),
            )
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.VALIDATION,
                message="صفحه خالی غیرمنتظره دریافت شد و کامل‌بودن استخراج قابل تأیید نیست.",
                retryable=True,
                url=fetched.url,
                page_number=page_number,
                details={
                    "attempts": attempts,
                    "reported_total_pages": summary["reported_total_pages"],
                    "parser_diagnostics": parsed_page.diagnostics,
                },
            )
            break

        page_warnings = list(parsed_page.warnings)
        if retry_attempts:
            page_warnings.append(f"recovered_after_{retry_attempts}_content_retries")
        page_status = (
            ExtractionPage.ParseStatus.WARNING
            if page_warnings
            else ExtractionPage.ParseStatus.SUCCEEDED
        )
        _create_page_record(
            run=run,
            connector=connector,
            page_number=page_number,
            fetched=fetched,
            parsed_page=parsed_page,
            attempts=attempts,
            parse_status=page_status,
            error_message=" | ".join(page_warnings),
        )
        summary["pages"] += 1
        summary["seen"] += len(parsed_page.notices)
        summary["warnings"] += len(parsed_page.warnings)

        for parsed in parsed_page.notices:
            detail = None
            if run.include_details and connector.supports_detail and parsed.detail_url:
                try:
                    detail_page = fetcher.fetch_detail(parsed.detail_url)
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

        previous_record_ids = record_ids
        summary["last_successful_page"] = page_number
        connector.last_successful_page = page_number
        connector.save(update_fields=["last_successful_page", "updated_at"])

        if parsed_page.end_of_results is True:
            summary["completeness"] = "complete"
            summary["stop_reason"] = "source_reported_end"
            break
    else:
        reported_total = summary["reported_total_pages"]
        if reported_total is not None and page_cap < reported_total:
            summary["status"] = "succeeded_with_warnings"
            summary["warnings"] += 1
            summary["completeness"] = "limited_by_page_cap"
            summary["stop_reason"] = "page_cap_before_reported_end"
        elif reported_total is None:
            summary["status"] = "succeeded_with_warnings"
            summary["warnings"] += 1
            summary["completeness"] = "page_cap_reached_unverified"
            summary["stop_reason"] = "page_cap_reached_without_total"
        else:
            summary["completeness"] = "complete"
            summary["stop_reason"] = "page_cap_reached_at_reported_end"

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
        if summary["status"] in {"failed", "partial"}:
            connector.status = ProcurementConnector.Status.ERROR
            connector.last_failure_at = now
            connector.save(update_fields=["status", "last_failure_at", "updated_at"])
        else:
            connector.status = ProcurementConnector.Status.ACTIVE
            connector.last_success_at = now
            connector.save(update_fields=["status", "last_success_at", "updated_at"])

    failed_connectors = [key for key, value in summaries.items() if value["status"] == "failed"]
    partial_connectors = [key for key, value in summaries.items() if value["status"] == "partial"]
    warning_connectors = [key for key, value in summaries.items() if value["status"] == "succeeded_with_warnings"]
    if not runnable:
        run.status = ExtractionRun.Status.CANCELLED
    elif len(failed_connectors) == len(runnable):
        run.status = ExtractionRun.Status.FAILED
    elif failed_connectors or partial_connectors:
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
    merged_summary = dict(run.summary or {})
    merged_summary.update(
        {
            "connectors": summaries,
            "skipped_disabled_connectors": skipped,
            "failed_connectors": failed_connectors,
            "partial_connectors": partial_connectors,
            "warning_connectors": warning_connectors,
        }
    )
    run.summary = merged_summary
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
        if any(item["status"] in {"failed", "partial"} for item in source_summaries):
            source.status = ProcurementSource.Status.DEGRADED
            source.last_failure_at = now
            source.save(update_fields=["status", "last_failure_at", "updated_at"])
        else:
            source.status = ProcurementSource.Status.ACTIVE
            source.last_success_at = now
            source.save(update_fields=["status", "last_success_at", "updated_at"])

    return {"run_id": str(run.id), "status": run.status, "summary": run.summary}
