import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = "PDP-One-Procurement/1.0 (+read-only public source collector)"


class SourceFetchError(Exception):
    def __init__(self, message: str, *, category: str, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.status_code = status_code


@dataclass(slots=True)
class FetchedPage:
    url: str
    status_code: int
    content: bytes
    text: str


class SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_host: str):
        super().__init__()
        self.allowed_host = allowed_host.lower()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl, self.allowed_host)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_public_dns(host: str) -> None:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise SourceFetchError(
            "Source host could not be resolved.",
            category="network",
            retryable=True,
        ) from exc
    if not addresses:
        raise SourceFetchError("Source host resolved to no address.", category="network", retryable=True)
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise SourceFetchError(
                "Source host resolved to a non-public network address.",
                category="validation",
                retryable=False,
            )


def validate_source_url(url: str, allowed_host: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = allowed_host.lower()
    if parsed.scheme != "https":
        raise SourceFetchError("Only HTTPS source URLs are allowed.", category="validation", retryable=False)
    if host != allowed and not host.endswith("." + allowed):
        raise SourceFetchError("Source URL host is outside the configured source domain.", category="validation", retryable=False)
    if parsed.username or parsed.password:
        raise SourceFetchError("Credentials in source URLs are not allowed.", category="validation", retryable=False)
    _validate_public_dns(host)


def fetch_public_html(
    url: str,
    *,
    allowed_host: str,
    timeout_seconds: int,
    retry_count: int,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchedPage:
    validate_source_url(url, allowed_host)
    opener = build_opener(SafeRedirectHandler(allowed_host))
    last_error: SourceFetchError | None = None

    for attempt in range(max(1, retry_count + 1)):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                final_url = response.geturl()
                validate_source_url(final_url, allowed_host)
                status_code = int(getattr(response, "status", 200))
                content_type_header = response.headers.get_content_type()
                if content_type_header not in {"text/html", "application/xhtml+xml"}:
                    raise SourceFetchError(
                        "Source returned a non-HTML response.",
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
                content_charset = response.headers.get_content_charset() or "utf-8"
                try:
                    text = content.decode(content_charset)
                except (LookupError, UnicodeDecodeError):
                    text = content.decode("utf-8", errors="replace")
                return FetchedPage(
                    url=final_url,
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
        except (URLError, TimeoutError, OSError) as exc:
            last_error = SourceFetchError(
                f"Source connection failed: {exc.__class__.__name__}.",
                category="network",
                retryable=True,
            )

        if last_error is None or not last_error.retryable or attempt >= retry_count:
            break
        time.sleep(min(2**attempt, 8))

    raise last_error or SourceFetchError(
        "Source request failed.",
        category="unexpected",
        retryable=False,
    )
