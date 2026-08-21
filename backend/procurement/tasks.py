import hashlib
import time
from datetime import timedelta
from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone

from procurement.connectors import parser_for
from procurement.connectors.fetchers import fetcher_for
from procurement.dates import parse_date_value
from procurement.http import SourceFetchError
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementSource, SourceNotice
from procurement.models_extraction import (
    ExtractionError,
    ExtractionPage,
    ExtractionRun,
    ExtractionRunItem,
)


HEZAREH_CONNECTOR_KEYS = frozenset({"hezareh_tenders", "hezareh_inquiries"})
HEZAREH_PRESERVED_DETAIL_FIELDS = (
    "description",
    "conditions",
    "employer",
    "document_deadline_raw",
    "opening_date_raw",
    "announcement_round",
    "notice_number",
    "source_label",
    "phone",
    "fax",
    "email",
    "website",
    "address",
)


def _record_error(
    run,
    connector,
    *,
    category,
    message,
    retryable,
    url="",
    page_number=None,
    details=None,
):
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


def _is_hezareh(connector: ProcurementConnector) -> bool:
    return connector.key in HEZAREH_CONNECTOR_KEYS


def _preserved_hezareh_detail(parsed, source_notice: SourceNotice | None) -> dict | None:
    """Reuse prior enrichment without allowing stale detail to override fresh list fields."""
    if source_notice is None:
        return None
    raw_payload = source_notice.raw_payload or {}
    if not isinstance(raw_payload, dict):
        return None
    previous_detail = raw_payload.get("detail") or {}
    if not isinstance(previous_detail, dict):
        return None

    preserved = {
        key: previous_detail[key]
        for key in HEZAREH_PRESERVED_DETAIL_FIELDS
        if previous_detail.get(key) not in (None, "")
    }
    for key in ("title", "province", "published_raw", "deadline_raw"):
        if not getattr(parsed, key, "") and previous_detail.get(key) not in (None, ""):
            preserved[key] = previous_detail[key]
    if previous_detail.get("detail_status"):
        preserved["detail_status"] = previous_detail["detail_status"]
    return preserved or None


def _content_retry_settings(source: ProcurementSource) -> tuple[int, int]:
    configuration = source.configuration or {}
    retry_count = _safe_int(configuration.get("content_retry_count"), 2)
    retry_delay_ms = _safe_int(configuration.get("content_retry_delay_ms"), 1200)
    return max(0, min(retry_count, 3)), max(0, min(retry_delay_ms, 5000))


def _hezareh_detail_enrichment_limit(source: ProcurementSource) -> int:
    configured = _safe_int((source.configuration or {}).get("hezareh_detail_enrichment_limit"), 10)
    return max(0, min(configured, 20))


def _list_page_url(connector: ProcurementConnector, page_number: int) -> str:
    configuration = connector.source.configuration or {}
    connector_urls = configuration.get("connector_page_urls") or {}
    route = connector_urls.get(connector.key) or {}
    if page_number == 1 and route.get("first_page"):
        return str(route["first_page"])
    template = route.get("template") or connector.list_url_template
    return str(template).format(page=page_number)


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
            except SourceFetchError:
                raise
            except Exception as exc:
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
                    return fetched, parsed_page, attempts, fetcher
                if attempt > retry_count:
                    return fetched, parsed_page, attempts, fetcher

        if attempt <= retry_count:
            if retry_delay_ms:
                time.sleep(retry_delay_ms / 1000)
            # Hezareh relies on ordinary cookie/session continuity. Retrying the
            # same list request must not create a brand-new public session.
            if not _is_hezareh(connector):
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


def _published_date(parsed):
    value, _ = parse_date_value(parsed.published_raw)
    return value


def _date_policy(run: ExtractionRun, connector: ProcurementConnector):
    first_run = not SourceNotice.objects.filter(connector=connector).exists()
    if run.mode == ExtractionRun.Mode.MANUAL_RANGE:
        cutoff = timezone.localdate() - timedelta(days=run.lookback_days or 1)
        return first_run, cutoff, "manual_range"
    if first_run:
        cutoff = timezone.localdate() - timedelta(days=1)
        return True, cutoff, "first_run_one_day"
    return False, None, "incremental_known_boundary"


def _enrich_hezareh_details_after_list(
    *,
    run: ExtractionRun,
    connector: ProcurementConnector,
    parser,
    allowed_host: str,
    candidates: list[tuple[object, int]],
    summary: dict,
):
    """Enrich a bounded set only after list completeness is established.

    Hezareh detail pages may present an ordinary security challenge. Detail
    enrichment therefore uses a separate public session and never controls list
    completeness. A challenge stops the enrichment phase without rewriting the
    already captured list record or prior enriched semantics.
    """
    summary["detail_candidates"] = len(candidates)
    limit = _hezareh_detail_enrichment_limit(connector.source)
    selected = candidates[:limit]
    summary["detail_deferred"] += max(0, len(candidates) - len(selected))
    if not selected:
        return

    detail_fetcher = fetcher_for(connector, allowed_host=allowed_host)
    delay_ms = _safe_int((connector.source.configuration or {}).get("detail_delay_ms"), 500)
    for index, (parsed, page_number) in enumerate(selected):
        summary["detail_attempted"] += 1
        try:
            detail_page = detail_fetcher.fetch_detail(parsed.detail_url)
            detail = parser.parse_detail(detail_page.text)
        except SourceFetchError as exc:
            summary["warnings"] += 1
            summary["detail_failed"] += 1
            _record_error(
                run,
                connector,
                category=exc.category,
                message="صفحه جزئیات هزاره دریافت نشد؛ رکورد فهرست و اطلاعات غنی‌شده قبلی حفظ شد.",
                retryable=exc.retryable,
                url=parsed.detail_url,
                page_number=page_number,
                details={"status_code": exc.status_code, "exception": exc.__class__.__name__},
            )
            continue
        except Exception as exc:
            summary["warnings"] += 1
            summary["detail_failed"] += 1
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.PARSE,
                message="صفحه جزئیات هزاره پردازش نشد؛ رکورد فهرست و اطلاعات غنی‌شده قبلی حفظ شد.",
                retryable=False,
                url=parsed.detail_url,
                page_number=page_number,
                details={"exception": exc.__class__.__name__},
            )
            continue

        if detail.get("detail_status") == "security_challenge":
            summary["warnings"] += 1
            summary["detail_access_limited"] += 1
            summary["detail_deferred"] += max(0, len(selected) - index - 1)
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.SECURITY_CHALLENGE,
                message="جزئیات هزاره با کد امنیتی محدود شد؛ پیمایش فهرست کامل باقی ماند و داده قبلی بازنویسی نشد.",
                retryable=True,
                url=parsed.detail_url,
                page_number=page_number,
                details={"detail_policy": "deferred_after_list_boundary"},
            )
            break

        if detail.get("detail_status") != "enriched":
            summary["warnings"] += 1
            summary["detail_failed"] += 1
            continue

        try:
            ingest_parsed_notice(
                connector,
                parsed,
                detail=detail,
                run=None,
                page_number=page_number,
            )
            summary["detail_enriched"] += 1
        except Exception as exc:
            summary["warnings"] += 1
            summary["detail_failed"] += 1
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.UNEXPECTED,
                message="جزئیات هزاره دریافت شد اما به‌روزرسانی غنی‌سازی ناموفق بود؛ داده فهرست حفظ شد.",
                retryable=True,
                url=parsed.detail_url or "",
                page_number=page_number,
                details={"exception": exc.__class__.__name__, "source_record_id": parsed.source_record_id},
            )

        if delay_ms > 0:
            time.sleep(min(delay_ms, 2000) / 1000)


def _execute_connector(
    run: ExtractionRun,
    connector: ProcurementConnector,
    *,
    hezareh_detail_jobs: list[dict] | None = None,
) -> dict:
    source = connector.source
    allowed_host = urlparse(source.base_url).hostname or ""
    parser = parser_for(connector.key, source.base_url, connector.notice_type)
    fetcher = fetcher_for(connector, allowed_host=allowed_host)
    page_cap = min(run.page_cap or connector.max_pages, connector.max_pages)
    first_run, cutoff_date, policy = _date_policy(run, connector)
    hezareh_deferred_details = bool(
        _is_hezareh(connector)
        and run.include_details
        and connector.supports_detail
    )
    summary = {
        "status": "succeeded",
        "mode": run.mode,
        "policy": policy,
        "first_run": first_run,
        "cutoff_date": cutoff_date.isoformat() if cutoff_date else None,
        "pages": 0,
        "seen": 0,
        "new": 0,
        "updated": 0,
        "duplicate": 0,
        "failed": 0,
        "skipped_outside_range": 0,
        "unknown_date_records": 0,
        "warnings": 0,
        "requested_page_cap": page_cap,
        "reported_total_pages": None,
        "reported_total_pages_source": "unknown",
        "last_successful_page": None,
        "stop_reason": "",
        "completeness": "unknown",
        "content_retry_attempts": 0,
        "recovered_pages": [],
        "suspicious_pages": [],
        "known_boundary_pages": 0,
        "detail_policy": "deferred_after_list_boundary" if hezareh_deferred_details else "inline",
        "detail_candidates": 0,
        "detail_attempted": 0,
        "detail_enriched": 0,
        "detail_access_limited": 0,
        "detail_failed": 0,
        "detail_deferred": 0,
    }
    previous_record_ids: tuple[str, ...] | None = None
    consecutive_known_pages = 0
    hezareh_detail_candidates: list[tuple[object, int]] = []

    for page_number in range(1, page_cap + 1):
        page_url = _list_page_url(connector, page_number)
        try:
            fetched, parsed_page, attempts, fetcher = _fetch_and_parse_with_content_retries(
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
            details = {"status_code": exc.status_code}
            if hasattr(exc, "as_details"):
                details.update(exc.as_details())
            _record_error(
                run,
                connector,
                category=exc.category,
                message=str(exc),
                retryable=exc.retryable,
                url=page_url,
                page_number=page_number,
                details=details,
            )
            summary["failed"] += 1
            summary["status"] = "failed"
            summary["completeness"] = "failed"
            summary["stop_reason"] = "fetch_or_validation_failed"
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
            total_source = str((parsed_page.diagnostics or {}).get("reported_total_pages_source") or "unknown")
            if total_source == "source_report" or summary["reported_total_pages_source"] != "source_report":
                summary["reported_total_pages"] = max(
                    summary["reported_total_pages"] or 0,
                    parsed_page.reported_total_pages,
                )
                summary["reported_total_pages_source"] = total_source

        original_notices = list(parsed_page.notices)
        record_ids = tuple(notice.source_record_id for notice in original_notices)
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
                parse_status=ExtractionPage.ParseStatus.WARNING,
                error_code="duplicate_page_content",
                error_message="محتوای این صفحه با صفحه قبلی یکسان بود؛ استخراج ناقص متوقف شد.",
            )
            _record_error(
                run,
                connector,
                category=ExtractionError.Category.VALIDATION,
                message="صفحه تکراری دریافت شد؛ استخراج برای جلوگیری از ثبت ناقص متوقف شد.",
                retryable=True,
                url=fetched.url,
                page_number=page_number,
                details={"attempts": attempts, "record_count": len(record_ids)},
            )
            break

        if not original_notices:
            natural_end = parsed_page.end_of_results is True
            summary["pages"] += 1
            if natural_end:
                summary["completeness"] = "complete"
                summary["stop_reason"] = "source_reported_end"
                _create_page_record(
                    run=run,
                    connector=connector,
                    page_number=page_number,
                    fetched=fetched,
                    parsed_page=parsed_page,
                    parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
                )
                break

            diagnostics = parsed_page.diagnostics or {}
            security_challenge = bool(diagnostics.get("security_challenge"))
            error_code = "security_challenge" if security_challenge else "unexpected_empty_page"
            error_category = (
                ExtractionError.Category.SECURITY_CHALLENGE
                if security_challenge
                else ExtractionError.Category.VALIDATION
            )
            error_message = (
                "فهرست هزاره با کد امنیتی/صفحه میانی محدود شد؛ استخراج بدون دورزدن کنترل امنیتی ناقص متوقف شد."
                if security_challenge
                else "صفحه بدون رکورد بود اما پایان واقعی فهرست تأیید نشد."
            )
            safe_message = (
                "فهرست هزاره با کنترل امنیتی محدود شد؛ استخراج به‌صورت fail-closed ناقص متوقف شد."
                if security_challenge
                else "صفحه خالی غیرمنتظره دریافت شد و کامل‌بودن استخراج قابل تأیید نیست."
            )
            summary["warnings"] += 1
            summary["status"] = "partial"
            summary["completeness"] = "incomplete"
            summary["stop_reason"] = error_code
            summary["suspicious_pages"].append(page_number)
            _create_page_record(
                run=run,
                connector=connector,
                page_number=page_number,
                fetched=fetched,
                parsed_page=parsed_page,
                parse_status=ExtractionPage.ParseStatus.WARNING,
                error_code=error_code,
                error_message=error_message,
            )
            _record_error(
                run,
                connector,
                category=error_category,
                message=safe_message,
                retryable=True,
                url=fetched.url,
                page_number=page_number,
                details={"attempts": attempts, "parser_diagnostics": diagnostics},
            )
            break

        dates = [_published_date(item) for item in original_notices]
        known_dates = [value for value in dates if value is not None]
        if cutoff_date and known_dates and max(known_dates) < cutoff_date:
            summary["pages"] += 1
            summary["completeness"] = "complete"
            summary["stop_reason"] = "date_boundary_reached"
            summary["skipped_outside_range"] += len(original_notices)
            _create_page_record(
                run=run,
                connector=connector,
                page_number=page_number,
                fetched=fetched,
                parsed_page=parsed_page,
                parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
                error_code="date_boundary_reached",
                error_message="تمام رکوردهای تاریخ‌دار صفحه قدیمی‌تر از مرز استخراج بودند.",
            )
            break

        selected_notices = []
        for parsed, published_date in zip(original_notices, dates):
            if cutoff_date and published_date is not None and published_date < cutoff_date:
                summary["skipped_outside_range"] += 1
                continue
            if cutoff_date and published_date is None:
                summary["unknown_date_records"] += 1
            selected_notices.append(parsed)

        page_warnings = list(parsed_page.warnings)
        if retry_attempts:
            page_warnings.append(f"recovered_after_{retry_attempts}_content_retries")
        if cutoff_date and any(value is None for value in dates):
            page_warnings.append("some_records_have_unverified_dates")
            summary["warnings"] += 1

        _create_page_record(
            run=run,
            connector=connector,
            page_number=page_number,
            fetched=fetched,
            parsed_page=parsed_page,
            parse_status=(
                ExtractionPage.ParseStatus.WARNING
                if page_warnings
                else ExtractionPage.ParseStatus.SUCCEEDED
            ),
            error_message=" | ".join(page_warnings),
        )
        summary["pages"] += 1
        summary["seen"] += len(selected_notices)
        summary["warnings"] += len(parsed_page.warnings)

        existing_by_record_id = {
            item.source_record_id: item
            for item in SourceNotice.objects.filter(
                connector=connector,
                source_record_id__in=[parsed.source_record_id for parsed in selected_notices],
            )
        }
        page_counts = {"new": 0, "updated": 0, "duplicate": 0, "failed": 0}
        for parsed in selected_notices:
            detail = None
            if hezareh_deferred_details:
                detail = _preserved_hezareh_detail(parsed, existing_by_record_id.get(parsed.source_record_id))
            elif run.include_details and connector.supports_detail and parsed.detail_url:
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
                source_notice, _, item_status = ingest_parsed_notice(
                    connector,
                    parsed,
                    detail=detail,
                    run=run,
                    page_number=page_number,
                )
                summary[item_status] += 1
                page_counts[item_status] += 1
                if (
                    hezareh_deferred_details
                    and parsed.detail_url
                    and item_status in {ExtractionRunItem.Status.NEW, ExtractionRunItem.Status.UPDATED}
                ):
                    hezareh_detail_candidates.append((parsed, page_number))
            except Exception as exc:
                summary["failed"] += 1
                page_counts["failed"] += 1
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

        if run.mode == ExtractionRun.Mode.INCREMENTAL and not first_run:
            if page_counts["new"] == 0 and page_counts["updated"] == 0 and page_counts["duplicate"] > 0:
                consecutive_known_pages += 1
                summary["known_boundary_pages"] = consecutive_known_pages
            else:
                consecutive_known_pages = 0
            if consecutive_known_pages >= 2:
                summary["completeness"] = "complete"
                summary["stop_reason"] = "known_data_boundary_reached"
                break

        if parsed_page.end_of_results is True:
            summary["completeness"] = "complete"
            summary["stop_reason"] = "source_reported_end"
            break
    else:
        reported_total = summary["reported_total_pages"]
        authoritative_total = (
            reported_total
            if summary["reported_total_pages_source"] == "source_report"
            else None
        )
        if authoritative_total is not None and page_cap < authoritative_total:
            summary["status"] = "succeeded_with_warnings"
            summary["warnings"] += 1
            summary["completeness"] = "limited_by_page_cap"
            summary["stop_reason"] = "page_cap_before_reported_end"
        elif authoritative_total is None:
            summary["status"] = "succeeded_with_warnings"
            summary["warnings"] += 1
            summary["completeness"] = "page_cap_reached_unverified"
            summary["stop_reason"] = "page_cap_reached_without_authoritative_total"
        else:
            summary["completeness"] = "complete"
            summary["stop_reason"] = "page_cap_reached_at_reported_end"

    if (
        hezareh_deferred_details
        and hezareh_detail_candidates
        and summary["completeness"] == "complete"
        and summary["status"] not in {"failed", "partial"}
    ):
        if hezareh_detail_jobs is not None:
            summary["detail_candidates"] = len(hezareh_detail_candidates)
            hezareh_detail_jobs.append(
                {
                    "connector": connector,
                    "parser": parser,
                    "allowed_host": allowed_host,
                    "candidates": list(hezareh_detail_candidates),
                    "summary": summary,
                }
            )
        else:
            _enrich_hezareh_details_after_list(
                run=run,
                connector=connector,
                parser=parser,
                allowed_host=allowed_host,
                candidates=hezareh_detail_candidates,
                summary=summary,
            )
    elif hezareh_deferred_details and hezareh_detail_candidates:
        summary["detail_candidates"] = len(hezareh_detail_candidates)
        summary["detail_deferred"] += len(hezareh_detail_candidates)

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
    hezareh_detail_jobs: list[dict] = []

    for connector in runnable:
        summary = _execute_connector(
            run,
            connector,
            hezareh_detail_jobs=hezareh_detail_jobs,
        )
        summaries[connector.key] = summary

    # Hezareh detail access can trigger source-side security limits. Keep list
    # discovery globally first so no detail request can prevent a later Hezareh
    # tender/inquiry connector from reaching its list boundary.
    for job in hezareh_detail_jobs:
        _enrich_hezareh_details_after_list(
            run=run,
            connector=job["connector"],
            parser=job["parser"],
            allowed_host=job["allowed_host"],
            candidates=job["candidates"],
            summary=job["summary"],
        )
        if job["summary"]["status"] == "succeeded" and job["summary"]["warnings"]:
            job["summary"]["status"] = "succeeded_with_warnings"

    for connector in runnable:
        summary = summaries[connector.key]
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
            "mode": run.mode,
            "lookback_days": run.lookback_days,
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
