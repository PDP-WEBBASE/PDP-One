import re
from datetime import date, datetime, time, timedelta

import jdatetime
from django.utils import timezone

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
DATE_RE = re.compile(r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})")
TIME_RE = re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?")
DAY_RE = re.compile(r"(?P<value>\d+)\s*روز")
HOUR_RE = re.compile(r"(?P<value>\d+)\s*ساعت")
MINUTE_RE = re.compile(r"(?P<value>\d+)\s*دقیقه")
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


def _relative_component(pattern: re.Pattern, value: str) -> int:
    match = pattern.search(value)
    return int(match.group("value")) if match else 0


def parse_deadline_value(raw_value: str) -> tuple[datetime | None, dict]:
    raw = (raw_value or "").strip()
    normalized = normalize_digits(raw)

    if any(unit in normalized for unit in ("روز", "ساعت", "دقیقه")):
        days = _relative_component(DAY_RE, normalized)
        hours = _relative_component(HOUR_RE, normalized)
        minutes = _relative_component(MINUTE_RE, normalized)
        if days or hours or minutes:
            duration = timedelta(days=days, hours=hours, minutes=minutes)
            deadline = timezone.now() + duration
            return deadline, {
                "raw_value": raw,
                "calendar_type": "relative_duration",
                "normalized_date": deadline.date().isoformat(),
                "normalized_datetime": deadline.isoformat(),
                "relative_seconds": int(duration.total_seconds()),
                "parse_status": "valid",
                "parse_error": "",
            }

    parsed_date, metadata = parse_date_value(raw_value)
    if parsed_date is None:
        return None, metadata

    time_match = TIME_RE.search(normalized)
    if time_match:
        try:
            parsed_time = time(
                int(time_match.group("hour")),
                int(time_match.group("minute")),
                int(time_match.group("second") or 0),
            )
        except ValueError as exc:
            metadata["parse_status"] = "invalid"
            metadata["parse_error"] = exc.__class__.__name__
            return None, metadata
    else:
        parsed_time = time(23, 59, 59)

    deadline = timezone.make_aware(
        datetime.combine(parsed_date, parsed_time),
        timezone.get_current_timezone(),
    )
    metadata["normalized_datetime"] = deadline.isoformat()
    return deadline, metadata
