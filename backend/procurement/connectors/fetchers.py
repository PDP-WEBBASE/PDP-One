import html as html_module
import re
import time
from http.client import RemoteDisconnected
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from procurement.http import (
    MAX_RESPONSE_BYTES,
    USER_AGENT,
    FetchedPage,
    SafeRedirectHandler,
    SourceFetchError,
    fetch_public_html,
    validate_source_url,
)


class GenericHtmlFetcher:
    def __init__(self, *, allowed_host: str, timeout_seconds: int, retry_count: int):
        self.allowed_host = allowed_host
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count

    def fetch_list(self, page_number: int, page_url: str) -> FetchedPage:
        return fetch_public_html(
            page_url,
            allowed_host=self.allowed_host,
            timeout_seconds=self.timeout_seconds,
            retry_count=self.retry_count,
        )

    def fetch_detail(self, detail_url: str) -> FetchedPage:
        return fetch_public_html(
            detail_url,
            allowed_host=self.allowed_host,
            timeout_seconds=self.timeout_seconds,
            retry_count=self.retry_count,
        )


class SessionFetcherBase:
    def __init__(self, *, allowed_host: str, timeout_seconds: int, retry_count: int):
        self.allowed_host = allowed_host
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.cookie_jar = CookieJar()
        self.opener = build_opener(
            HTTPCookieProcessor(self.cookie_jar),
            SafeRedirectHandler(allowed_host),
        )

    def _fetch(
        self,
        request: Request,
        *,
        expected_content_types: set[str],
        safe_url: str | None = None,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> FetchedPage:
        validate_source_url(request.full_url, self.allowed_host)
        last_error: SourceFetchError | None = None
        for attempt in range(max(1, self.retry_count + 1)):
            try:
                with self.opener.open(request, timeout=self.timeout_seconds) as response:
                    final_url = response.geturl()
                    validate_source_url(final_url, self.allowed_host)
                    status_code = int(getattr(response, "status", 200))
                    content_type = response.headers.get_content_type()
                    if content_type not in expected_content_types:
                        raise SourceFetchError(
                            f"Source returned unexpected content type: {content_type}.",
                            category="validation",
                            retryable=False,
                            status_code=status_code,
                        )
                    content = response.read(max_bytes + 1)
                    if len(content) > max_bytes:
                        raise SourceFetchError(
                            "Source response exceeded the safe size limit.",
                            category="validation",
                            retryable=False,
                            status_code=status_code,
                        )
                    charset = response.headers.get_content_charset() or "utf-8"
                    try:
                        text = content.decode(charset)
                    except (LookupError, UnicodeDecodeError):
                        text = content.decode("utf-8", errors="replace")
                    return FetchedPage(
                        url=safe_url or final_url,
                        status_code=status_code,
                        content=content,
                        text=text,
                    )
            except SourceFetchError:
                raise
            except HTTPError as exc:
                last_error = SourceFetchError(
                    f"Source returned HTTP {exc.code}.",
                    category="http",
                    retryable=500 <= exc.code < 600 or exc.code == 429,
                    status_code=exc.code,
                )
            except (URLError, TimeoutError, OSError, RemoteDisconnected) as exc:
                last_error = SourceFetchError(
                    f"Source connection failed: {exc.__class__.__name__}.",
                    category="network",
                    retryable=True,
                )
            except Exception as exc:
                last_error = SourceFetchError(
                    f"Source request failed: {exc.__class__.__name__}.",
                    category="unexpected",
                    retryable=False,
                )
            if last_error is None or not last_error.retryable or attempt >= self.retry_count:
                break
            time.sleep(min(2**attempt, 8))
        raise last_error or SourceFetchError(
            "Source request failed.", category="unexpected", retryable=False
        )

    def fetch_detail(self, detail_url: str) -> FetchedPage:
        request = Request(
            detail_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        return self._fetch(
            request,
            expected_content_types={"text/html", "application/xhtml+xml"},
        )


class SetadEtendFetcher(SessionFetcherBase):
    INDEX_URL = "https://etend.setadiran.ir/etend/index.action"
    WELCOME_URL = "https://etend.setadiran.ir/etend/welcome.action"
    LIST_URL = "https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action"
    TOKEN_PATTERNS = (
        re.compile(
            r'<input\b(?=[^>]*\bname\s*=\s*["\']csrf_token["\'])[^>]*\bvalue\s*=\s*["\']([^"\']+)["\'][^>]*>',
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(r'["\']csrf_token["\']\s*[,=:]\s*["\']([A-Za-z0-9_-]+)["\']', re.IGNORECASE),
    )

    def __init__(self, *, allowed_host: str, timeout_seconds: int, retry_count: int, rows: int = 30):
        super().__init__(
            allowed_host=allowed_host,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
        )
        self.rows = rows
        self.csrf_token = ""

    def _ensure_session(self) -> None:
        if self.csrf_token:
            return
        index_request = Request(
            self.INDEX_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        self._fetch(
            index_request,
            expected_content_types={"text/html", "application/xhtml+xml"},
            safe_url=self.INDEX_URL,
        )
        welcome_request = Request(
            self.WELCOME_URL,
            data=b"",
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, */*; q=0.01",
                "Referer": self.INDEX_URL,
                "Origin": "https://etend.setadiran.ir",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Length": "0",
            },
        )
        welcome = self._fetch(
            welcome_request,
            expected_content_types={"text/html", "application/xhtml+xml"},
            safe_url=self.WELCOME_URL,
        )
        for pattern in self.TOKEN_PATTERNS:
            match = pattern.search(welcome.text)
            if match:
                self.csrf_token = match.group(1)
                break
        if not self.csrf_token:
            raise SourceFetchError(
                "SETAD eTender CSRF token was not available in the public session.",
                category="security_challenge",
                retryable=True,
            )

    def fetch_list(self, page_number: int, page_url: str) -> FetchedPage:
        self._ensure_session()
        milliseconds = int(time.time() * 1000)
        query = urlencode(
            {
                "struts.token.name": "csrf_token",
                "csrf_token": self.csrf_token,
                "_search": "false",
                "nd": milliseconds,
                "rows": self.rows,
                "page": page_number,
                "sidx": "",
                "sord": "asc",
                "_": milliseconds,
            }
        )
        request_url = f"{self.LIST_URL}?{query}"
        request = Request(
            request_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": self.INDEX_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        safe_url = f"{self.LIST_URL}?page={page_number}&rows={self.rows}"
        return self._fetch(
            request,
            expected_content_types={"application/json", "text/json"},
            safe_url=safe_url,
        )


class SetadEprocFetcher(SessionFetcherBase):
    BASE_LIST_URL = "https://eproc.setadiran.ir/eproc/needs.do"
    PAGE_PARAMETER_RE = re.compile(r"[?&](d-\d+-p)=\d+")

    def __init__(self, *, allowed_host: str, timeout_seconds: int, retry_count: int):
        super().__init__(
            allowed_host=allowed_host,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
        )
        self.first_page: FetchedPage | None = None
        self.page_parameter = ""

    def _fetch_html(self, url: str, *, safe_url: str | None = None) -> FetchedPage:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        return self._fetch(
            request,
            expected_content_types={"text/html", "application/xhtml+xml"},
            safe_url=safe_url,
        )

    def _ensure_first_page(self) -> None:
        if self.first_page is not None:
            return
        self.first_page = self._fetch_html(self.BASE_LIST_URL, safe_url=self.BASE_LIST_URL)
        decoded = html_module.unescape(self.first_page.text)
        match = self.PAGE_PARAMETER_RE.search(decoded)
        if match:
            self.page_parameter = match.group(1)

    def fetch_list(self, page_number: int, page_url: str) -> FetchedPage:
        self._ensure_first_page()
        if page_number <= 1 and self.first_page is not None:
            return self.first_page
        if not self.page_parameter:
            raise SourceFetchError(
                "SETAD eProc pagination parameter was not found.",
                category="parse",
                retryable=False,
            )
        query = urlencode({"pager": "true", self.page_parameter: page_number})
        url = f"{self.BASE_LIST_URL}?{query}"
        return self._fetch_html(url, safe_url=url)


def fetcher_for(connector, *, allowed_host: str):
    options = {
        "allowed_host": allowed_host,
        "timeout_seconds": connector.timeout_seconds,
        "retry_count": connector.retry_count,
    }
    if connector.key == "setad_tenders":
        return SetadEtendFetcher(rows=connector.page_size_hint or 30, **options)
    if connector.key == "setad_inquiries":
        return SetadEprocFetcher(**options)
    return GenericHtmlFetcher(**options)
