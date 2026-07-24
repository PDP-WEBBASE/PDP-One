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


def merge_parsed_notice(parsed: ParsedNotice, detail: dict | None = None) -> dict:
    detail = detail or {}
    title = normalize_text(detail.get("title")) or parsed.title
    employer = normalize_text(detail.get("employer")) or parsed.employer
    province = normalize_text(detail.get("province")) or parsed.province
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
    payload["content_hash"] = stable_hash(
        {
            key: payload[key]
            for key in (
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
        }
    )
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
    source_values = {
        "source_url": payload["source_url"],
        "detail_url": payload["detail_url"],
        "source_declared_type": payload["source_declared_type"],
        "title_raw": payload["title"],
        "employer_raw": payload["employer"],
        "province_raw": payload["province"],
        "published_at_raw": payload["published_raw"],
        "deadline_raw": payload["deadline_raw"],
        "raw_payload": payload["raw_payload"],
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
    if created:
        item_status = ExtractionRunItem.Status.NEW
        changed_fields = list(source_values.keys())
    else:
        changed_fields = _changed_fields(source_notice, source_values)
        item_status = ExtractionRunItem.Status.UPDATED if changed_fields else ExtractionRunItem.Status.DUPLICATE
        for field, value in source_values.items():
            setattr(source_notice, field, value)
        source_notice.save(update_fields=SOURCE_FIELDS + ["updated_at"])

    if created or changed_fields:
        next_revision = (
            source_notice.revisions.aggregate(maximum=Max("revision_number"))["maximum"] or 0
        ) + 1
        SourceNoticeRevision.objects.create(
            source_notice=source_notice,
            revision_number=next_revision,
            content_hash=payload["content_hash"],
            raw_payload=payload["raw_payload"],
            parsed_payload=payload,
            changed_fields=changed_fields,
            parser_version=connector.parser_version,
            captured_at=now,
        )

    resolved_type = payload["content_detected_type"] or payload["source_declared_type"]
    published_date, published_meta = parse_date_value(payload["published_raw"])
    submission_deadline, deadline_meta = parse_deadline_value(payload["deadline_raw"])

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
            changed_fields=changed_fields,
        )

    return source_notice, notice, item_status
