from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from procurement.connectors.base import normalize_text, stable_hash
from procurement.connectors.types import ParsedNotice
from procurement.dates import parse_date_value, parse_deadline_value
from procurement.models import (
    NoticeSourceLink,
    ProcurementNotice,
    SourceNotice,
    SourceNoticeRevision,
)
from procurement.models_extraction import ExtractionRun, ExtractionRunItem

SOURCE_FIELDS = [
    "source_url",
    "detail_url",
    "source_declared_type",
    "title_raw",
    "employer_raw",
    "province_raw",
    "published_at_raw",
    "deadline_raw",
    "raw_payload",
    "content_hash",
    "detail_status",
    "last_seen_at",
    "is_active",
]

SEMANTIC_HASH_FIELDS = (
    "source_record_id",
    "detail_url",
    "source_declared_type",
    "content_detected_type",
    "title",
    "employer",
    "province",
    "published_raw",
    "deadline_raw",
    "description",
    "conditions",
    "notice_number",
    "contact_text",
    "detail_status",
)
SETAD_EPROC_SEMANTIC_MARKER_KEY = "setad_eproc_semantic_hash_without_deadline"
SETAD_EPROC_COUNTDOWN_TOLERANCE_SECONDS = 300
SETAD_ETEND_LIFECYCLE_MARKER_KEY = "setad_etend_lifecycle_v1"
SETAD_ETEND_LIFECYCLE_FIELDS = (
    "operationCityName",
    "type",
    "typeName",
    "documentsDeadlineDate",
    "proposalDeadlineDate",
    "evaluationDeadlineDate",
    "openingDate",
    "allowedContractor",
    "allowedConsultation",
    "allowedCommodity",
    "allowedServices",
)


def _semantic_hash(payload: dict, *, include_deadline: bool = True) -> str:
    fields = SEMANTIC_HASH_FIELDS if include_deadline else tuple(
        key for key in SEMANTIC_HASH_FIELDS if key != "deadline_raw"
    )
    return stable_hash({key: payload.get(key) for key in fields})


def _setad_etend_lifecycle_projection(raw_payload: dict | None) -> dict:
    if not isinstance(raw_payload, dict):
        return {}
    list_payload = raw_payload.get("list") or {}
    if not isinstance(list_payload, dict):
        return {}
    projection = {}
    for field in SETAD_ETEND_LIFECYCLE_FIELDS:
        value = list_payload.get(field)
        if isinstance(value, str):
            value = normalize_text(value)
        projection[field] = value
    return projection


def _setad_etend_lifecycle_state(payload: dict) -> dict:
    return {
        "version": 1,
        "core_hash": payload["content_hash"],
        "projection": _setad_etend_lifecycle_projection(payload.get("raw_payload")),
    }


def _source_raw_payload_with_internal(raw_payload: dict, key: str, value) -> dict:
    stored = dict(raw_payload or {})
    internal = dict(stored.get("_pdp") or {})
    internal[key] = value
    stored["_pdp"] = internal
    return stored


def _source_raw_payload_with_semantic_marker(raw_payload: dict, marker: str) -> dict:
    return _source_raw_payload_with_internal(
        raw_payload,
        SETAD_EPROC_SEMANTIC_MARKER_KEY,
        marker,
    )


def _setad_etend_effective_hash(payload: dict, source_notice: SourceNotice | None) -> str:
    """Hash material eTender lifecycle fields without a first-deploy mass update.

    Historical SETAD tender rows already retain the public JSON row in
    ``raw_payload.list``. For an existing pre-safeguard row, compare the current
    lifecycle projection to that retained evidence. If both the legacy core hash
    and lifecycle projection are unchanged, keep the existing hash and only add
    the internal marker to latest SourceNotice evidence. A real lifecycle change
    receives a deterministic new hash and therefore a new semantic revision.
    """

    state = _setad_etend_lifecycle_state(payload)
    if source_notice is None:
        return stable_hash(
            {
                "core_hash": state["core_hash"],
                "setad_etend_lifecycle": state["projection"],
            }
        )

    previous_raw = source_notice.raw_payload if isinstance(source_notice.raw_payload, dict) else {}
    previous_internal = previous_raw.get("_pdp") or {}
    previous_state = previous_internal.get(SETAD_ETEND_LIFECYCLE_MARKER_KEY)
    if isinstance(previous_state, dict) and previous_state.get("version") == 1:
        unchanged = (
            previous_state.get("core_hash") == state["core_hash"]
            and previous_state.get("projection") == state["projection"]
        )
    else:
        unchanged = (
            source_notice.content_hash == state["core_hash"]
            and _setad_etend_lifecycle_projection(previous_raw) == state["projection"]
        )

    if unchanged:
        return source_notice.content_hash
    return stable_hash(
        {
            "core_hash": state["core_hash"],
            "setad_etend_lifecycle": state["projection"],
        }
    )


def merge_parsed_notice(parsed: ParsedNotice, detail: dict | None = None) -> dict:
    detail = detail or {}
    title = normalize_text(detail.get("title")) or parsed.title
    employer = normalize_text(detail.get("employer")) or parsed.employer
    province = normalize_text(detail.get("province")) or parsed.province
    city = normalize_text(detail.get("city")) or normalize_text((parsed.metadata or {}).get("city"))
    published_raw = normalize_text(detail.get("published_raw")) or parsed.published_raw
    deadline_raw = normalize_text(detail.get("deadline_raw")) or parsed.deadline_raw
    detected_type = detail.get("content_detected_type") or parsed.content_detected_type
    resolution_status = detail.get("type_resolution_status") or parsed.type_resolution_status
    contact_parts = [detail.get("phone"), detail.get("email"), detail.get("address")]
    contact_text = " | ".join(normalize_text(value) for value in contact_parts if normalize_text(value))
    payload = {
        "source_record_id": parsed.source_record_id,
        "source_url": parsed.source_url,
        "detail_url": normalize_text(detail.get("detail_url")) or parsed.detail_url,
        "source_declared_type": parsed.source_declared_type,
        "content_detected_type": detected_type,
        "type_resolution_status": resolution_status,
        "title": title,
        "employer": employer,
        "province": province,
        "city": city,
        "published_raw": published_raw,
        "deadline_raw": deadline_raw,
        "summary": parsed.summary,
        "description": normalize_text(detail.get("description")) or parsed.description,
        "conditions": normalize_text(detail.get("conditions")) or parsed.conditions,
        "notice_number": normalize_text(detail.get("notice_number")) or parsed.notice_number,
        "contact_text": contact_text or parsed.contact_text,
        "detail_status": detail.get("detail_status") or parsed.detail_status,
        "metadata": {**parsed.metadata, "detail": {key: value for key, value in detail.items() if key != "json_ld"}},
        "raw_payload": {"list": parsed.raw_payload, "detail": detail},
    }
    payload["content_hash"] = _semantic_hash(payload)
    return payload


def _changed_fields(instance: SourceNotice, values: dict) -> list[str]:
    changed = []
    for field in SOURCE_FIELDS:
        if field == "last_seen_at":
            continue
        if getattr(instance, field) != values[field]:
            changed.append(field)
    return changed


def _find_exact_notice(payload: dict, resolved_type: str):
    notice_number = normalize_text(payload.get("notice_number"))
    employer = normalize_text(payload.get("employer"))
    if not notice_number or not employer:
        return None
    return ProcurementNotice.objects.filter(
        resolved_notice_type=resolved_type,
        notice_number=notice_number,
        employer_name=employer,
        soft_deleted_at__isnull=True,
    ).first()


def _relative_deadline_granularity_seconds(raw_value: str) -> int:
    value = normalize_text(raw_value)
    if "دقیقه" in value:
        return 60
    if "ساعت" in value:
        return 60 * 60
    if "روز" in value:
        return 24 * 60 * 60
    return 0


def _relative_deadline_window(raw_value: str, observed_at):
    _, metadata = parse_deadline_value(raw_value)
    if metadata.get("calendar_type") != "relative_duration":
        return None
    relative_seconds = metadata.get("relative_seconds")
    granularity_seconds = _relative_deadline_granularity_seconds(raw_value)
    if relative_seconds is None or granularity_seconds <= 0:
        return None
    start = observed_at + timedelta(seconds=int(relative_seconds))
    end = start + timedelta(seconds=granularity_seconds)
    return start, end


def _natural_relative_deadline_progression(
    *,
    previous_raw: str,
    current_raw: str,
    previous_seen_at,
    current_seen_at,
) -> bool:
    """Return true when two countdown observations can describe one deadline.

    SETAD eProc publishes a decreasing duration rather than an absolute deadline.
    Treat each displayed duration as a deadline window whose width is the smallest
    displayed unit. Natural passage of time keeps the two windows overlapping;
    a real extension/change moves the window away from the previous one.
    """

    if not previous_raw or not current_raw or previous_seen_at is None:
        return False
    previous_window = _relative_deadline_window(previous_raw, previous_seen_at)
    current_window = _relative_deadline_window(current_raw, current_seen_at)
    if previous_window is None or current_window is None:
        return False

    tolerance = timedelta(seconds=SETAD_EPROC_COUNTDOWN_TOLERANCE_SECONDS)
    previous_start, previous_end = previous_window
    current_start, current_end = current_window
    return (
        previous_start <= current_end + tolerance
        and current_start <= previous_end + tolerance
    )


def _is_setad_eproc(parsed: ParsedNotice) -> bool:
    return (parsed.metadata or {}).get("setad_channel") == "eproc"


def _is_setad_etend(connector, parsed: ParsedNotice) -> bool:
    return connector.key == "setad_tenders" and (parsed.metadata or {}).get("setad_channel") == "etend"


def _previous_setad_semantic_marker(source_notice: SourceNotice) -> str:
    raw_payload = source_notice.raw_payload or {}
    marker = ((raw_payload.get("_pdp") or {}).get(SETAD_EPROC_SEMANTIC_MARKER_KEY) or "")
    if marker:
        return str(marker)

    # Existing records created before this safeguard do not yet have the marker.
    # Bootstrap it from the latest semantic revision once; subsequent runs read the
    # marker directly from SourceNotice and do not need this fallback query.
    latest_revision = source_notice.revisions.order_by("-revision_number").only("parsed_payload").first()
    if latest_revision is None or not isinstance(latest_revision.parsed_payload, dict):
        return ""
    return _semantic_hash(latest_revision.parsed_payload, include_deadline=False)


def _preserve_unchanged_relative_deadline(
    *,
    source_link: NoticeSourceLink | None,
    notice: ProcurementNotice,
    parsed_deadline,
    deadline_meta: dict,
    natural_relative_progression: bool = False,
):
    """Keep the materialized deadline when a relative countdown is unchanged.

    For ordinary sources, exact raw-duration equality retains the prior behavior.
    For SETAD eProc, a naturally decreasing countdown may have a different raw
    string every hour; the caller supplies `natural_relative_progression` only
    after validating the previous/current countdown windows.
    """

    if source_link is None or parsed_deadline is None or notice.submission_deadline is None:
        return parsed_deadline, deadline_meta
    if deadline_meta.get("calendar_type") != "relative_duration":
        return parsed_deadline, deadline_meta

    previous_meta = ((notice.date_metadata or {}).get("deadline") or {})
    if previous_meta.get("calendar_type") != "relative_duration":
        return parsed_deadline, deadline_meta

    same_raw_duration = previous_meta.get("raw_value") == deadline_meta.get("raw_value")
    if not same_raw_duration and not natural_relative_progression:
        return parsed_deadline, deadline_meta

    stable_deadline = notice.submission_deadline
    return stable_deadline, {
        **deadline_meta,
        "normalized_date": stable_deadline.date().isoformat(),
        "normalized_datetime": stable_deadline.isoformat(),
        "stability_source": (
            "preserved_progressing_relative_deadline"
            if natural_relative_progression and not same_raw_duration
            else "preserved_existing_relative_deadline"
        ),
    }


@transaction.atomic
def ingest_parsed_notice(
    connector,
    parsed: ParsedNotice,
    *,
    detail: dict | None = None,
    run: ExtractionRun | None = None,
    page_number: int | None = None,
) -> tuple[SourceNotice, ProcurementNotice, str]:
    payload = merge_parsed_notice(parsed, detail)
    now = timezone.now()
    setad_eproc = _is_setad_eproc(parsed)
    setad_etend = _is_setad_etend(connector, parsed)
    semantic_marker = _semantic_hash(payload, include_deadline=False) if setad_eproc else ""

    source_raw_payload = payload["raw_payload"]
    if setad_eproc:
        source_raw_payload = _source_raw_payload_with_semantic_marker(source_raw_payload, semantic_marker)
    if setad_etend:
        source_raw_payload = _source_raw_payload_with_internal(
            source_raw_payload,
            SETAD_ETEND_LIFECYCLE_MARKER_KEY,
            _setad_etend_lifecycle_state(payload),
        )

    source_values = {
        "source_url": payload["source_url"],
        "detail_url": payload["detail_url"],
        "source_declared_type": payload["source_declared_type"],
        "title_raw": payload["title"],
        "employer_raw": payload["employer"],
        "province_raw": payload["province"],
        "published_at_raw": payload["published_raw"],
        "deadline_raw": payload["deadline_raw"],
        "raw_payload": source_raw_payload,
        "content_hash": payload["content_hash"],
        "detail_status": payload["detail_status"],
        "last_seen_at": now,
        "is_active": True,
    }
    source_notice, created = SourceNotice.objects.get_or_create(
        connector=connector,
        source_record_id=payload["source_record_id"],
        defaults={**source_values, "first_seen_at": now},
    )

    if setad_etend:
        payload["content_hash"] = _setad_etend_effective_hash(
            payload,
            None if created else source_notice,
        )
        source_values["content_hash"] = payload["content_hash"]

    natural_relative_progression = False
    if created:
        # eTender effective hashing is computed after identity lookup so existing
        # legacy rows can bootstrap without churn. A newly-created eTender row is
        # therefore updated once in-place before its first semantic revision.
        if setad_etend:
            for field, value in source_values.items():
                setattr(source_notice, field, value)
            source_notice.save(update_fields=SOURCE_FIELDS + ["updated_at"])
        changed_fields = list(source_values.keys())
        semantic_changed_fields = changed_fields
        item_status = ExtractionRunItem.Status.NEW
    else:
        previous_content_hash = source_notice.content_hash
        previous_deadline_raw = source_notice.deadline_raw
        previous_seen_at = source_notice.last_seen_at

        if setad_eproc:
            natural_relative_progression = _natural_relative_deadline_progression(
                previous_raw=previous_deadline_raw,
                current_raw=payload["deadline_raw"],
                previous_seen_at=previous_seen_at,
                current_seen_at=now,
            )
            if natural_relative_progression:
                previous_marker = _previous_setad_semantic_marker(source_notice)
                if previous_marker and previous_marker == semantic_marker:
                    # Preserve the last true semantic hash while still storing the
                    # newest raw countdown and last-seen evidence on SourceNotice.
                    payload["content_hash"] = previous_content_hash
                    source_values["content_hash"] = previous_content_hash

        changed_fields = _changed_fields(source_notice, source_values)
        semantic_changed = previous_content_hash != payload["content_hash"]
        semantic_changed_fields = changed_fields if semantic_changed else []
        item_status = (
            ExtractionRunItem.Status.UPDATED
            if semantic_changed
            else ExtractionRunItem.Status.DUPLICATE
        )
        for field, value in source_values.items():
            setattr(source_notice, field, value)
        source_notice.save(update_fields=SOURCE_FIELDS + ["updated_at"])

    # Source list-page movement, raw capture drift, internal semantic markers and a
    # natural SETAD countdown are latest-state evidence rather than revisions.
    if created or semantic_changed_fields:
        next_revision = (
            source_notice.revisions.aggregate(maximum=Max("revision_number"))["maximum"] or 0
        ) + 1
        SourceNoticeRevision.objects.create(
            source_notice=source_notice,
            revision_number=next_revision,
            content_hash=payload["content_hash"],
            raw_payload=payload["raw_payload"],
            parsed_payload=payload,
            changed_fields=semantic_changed_fields,
            parser_version=connector.parser_version,
            captured_at=now,
        )

    resolved_type = payload["content_detected_type"] or payload["source_declared_type"]
    source_link = NoticeSourceLink.objects.filter(source_notice=source_notice).select_related("procurement_notice").first()
    if source_link is not None:
        notice = source_link.procurement_notice
    else:
        notice = _find_exact_notice(payload, resolved_type)
        if notice is None:
            notice = ProcurementNotice(
                resolved_notice_type=resolved_type,
                title=payload["title"],
                first_seen_at=now,
                last_seen_at=now,
            )

    published_date, published_meta = parse_date_value(payload["published_raw"])
    submission_deadline, deadline_meta = parse_deadline_value(payload["deadline_raw"])
    submission_deadline, deadline_meta = _preserve_unchanged_relative_deadline(
        source_link=source_link,
        notice=notice,
        parsed_deadline=submission_deadline,
        deadline_meta=deadline_meta,
        natural_relative_progression=natural_relative_progression,
    )

    notice.resolved_notice_type = resolved_type
    notice.type_resolution_status = payload["type_resolution_status"]
    notice.title = payload["title"]
    notice.normalized_title = normalize_text(payload["title"])
    notice.summary = payload["summary"]
    notice.description = payload["description"]
    notice.conditions = payload["conditions"]
    notice.employer_name = payload["employer"]
    notice.notice_number = payload["notice_number"]
    notice.province = payload["province"]
    if payload["city"]:
        notice.city = payload["city"]
    notice.published_date = published_date
    notice.submission_deadline = submission_deadline
    notice.date_metadata = {"published": published_meta, "deadline": deadline_meta}
    notice.contact_text = payload["contact_text"]
    notice.processing_status = (
        ProcurementNotice.ProcessingStatus.NORMALIZED
        if payload["type_resolution_status"] == ProcurementNotice.TypeResolutionStatus.NEEDS_REVIEW
        else ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS
    )
    notice.last_seen_at = now
    notice.save()

    if source_link is None:
        NoticeSourceLink.objects.create(
            procurement_notice=notice,
            source_notice=source_notice,
            match_type=NoticeSourceLink.MatchType.EXACT,
            confidence=100,
            rationale="same-source identity or exact notice number and employer",
        )

    if run is not None:
        ExtractionRunItem.objects.create(
            run=run,
            connector=connector,
            source_notice=source_notice,
            source_record_id=payload["source_record_id"],
            page_number=page_number,
            position=parsed.position,
            status=item_status,
            changed_fields=semantic_changed_fields,
        )

    return source_notice, notice, item_status
