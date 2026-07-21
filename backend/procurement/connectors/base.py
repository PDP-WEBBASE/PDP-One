import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin

PERSIAN_TRANSLATION = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
SPACE_RE = re.compile(r"\s+")
DIGIT_RE = re.compile(r"\d+")


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
