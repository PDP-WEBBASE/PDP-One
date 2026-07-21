import re
from datetime import date, datetime, time

import jdatetime
from django.utils import timezone

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
DATE_RE = re.compile(r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})")
MISSING_TERMS = {"", "اعلام نشده", "رجوع به آگهی", "نامشخص", "تعیین نشده", "-", "—"}


def normalize_digits(value: str) -> str:
    return (value or "").translate(DIGIT_TRANSLATION).strip()


def parse_date_value(raw_value: str) -> tuple[date | None, dict]:
    raw = (raw_value or "").strip()
    normalized = normalize_digits(raw)
    metadata = {
        "raw_value": raw,
        "calendar_type": "unknown",
        "normalized_date": None,
        "parse_status": "missing" if normalized in MISSING_TERMS else "invalid",
        "parse_error": "",
    }
    if normalized in MISSING_TERMS:
        return None, metadata

    match = DATE_RE.search(normalized)
    if not match:
        metadata["parse_error"] = "date_pattern_not_found"
        return None, metadata

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        if 1300 <= year <= 1499:
            parsed = jdatetime.date(year, month, day).togregorian()
            metadata["calendar_type"] = "jalali"
        elif 1900 <= year <= 2200:
            parsed = date(year, month, day)
            metadata["calendar_type"] = "gregorian"
        else:
            metadata["parse_status"] = "ambiguous"
            metadata["parse_error"] = "unsupported_year"
            return None, metadata
    except (ValueError, OverflowError) as exc:
        metadata["parse_error"] = exc.__class__.__name__
        return None, metadata

    metadata["normalized_date"] = parsed.isoformat()
    metadata["parse_status"] = "valid"
    return parsed, metadata


def parse_deadline_value(raw_value: str) -> tuple[datetime | None, dict]:
    parsed_date, metadata = parse_date_value(raw_value)
    if parsed_date is None:
        return None, metadata
    deadline = datetime.combine(parsed_date, time(23, 59, 59))
    return timezone.make_aware(deadline, timezone.get_current_timezone()), metadata
