import hashlib
import json
import re
from typing import Any, Iterable
from urllib.parse import parse_qs, urljoin, urlparse

PERSIAN_TRANSLATION = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
SPACE_RE = re.compile(r"\s+")
DIGIT_RE = re.compile(r"\d+")
PAGE_PATH_RE = re.compile(r"(?:^|[\/_-])page(?:[\/_-])?(\d+)(?:$|[\/?#_-])", re.IGNORECASE)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).translate(PERSIAN_TRANSLATION).replace("\u200c", " ").replace("\ufeff", "")
    return SPACE_RE.sub(" ", text).strip()


def absolute_url(base_url: str, href: str | None) -> str:
    return urljoin(base_url.rstrip("/") + "/", href or "")


def canonicalize_hezareh_url(url: str) -> str:
    return url.replace("/-!/", "/-%21/")


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def detect_notice_type(text: str, declared_type: str) -> tuple[str | None, str]:
    normalized = normalize_text(text).lower()
    inquiry = any(token in normalized for token in ("استعلام", "درخواست قیمت", "استعلام بها"))
    tender = any(token in normalized for token in ("مناقصه", "مزایده"))
    if inquiry and not tender:
        detected = "inquiry"
    elif tender and not inquiry:
        detected = "tender"
    else:
        detected = None
    status = "needs_review" if detected and detected != declared_type else "resolved"
    return detected, status


def first_numeric(value: str) -> str:
    match = DIGIT_RE.search(normalize_text(value))
    return match.group(0) if match else ""


def first_date(value: str) -> str:
    normalized = normalize_text(value)
    match = re.search(r"(?:13|14|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}", normalized)
    return match.group(0) if match else normalized


def page_number_from_url(url: str, default: int | None = None) -> int | None:
    """Extract a likely page number without depending on a source-specific parameter name."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    preferred_values: list[str] = []
    fallback_values: list[str] = []
    for key, values in query.items():
        lowered = key.lower()
        if "page" in lowered or "pager" in lowered:
            preferred_values.extend(values)
        elif lowered in {"p", "offset"}:
            fallback_values.extend(values)
    for value in preferred_values + fallback_values:
        if str(value).isdigit():
            number = int(value)
            if number >= 0:
                return number

    match = PAGE_PATH_RE.search(parsed.path)
    if match:
        return int(match.group(1))
    return default


def pagination_page_numbers(urls: Iterable[str]) -> list[int]:
    numbers = {
        number
        for number in (page_number_from_url(url) for url in urls)
        if number is not None
    }
    return sorted(numbers)
