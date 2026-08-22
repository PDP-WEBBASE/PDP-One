import hashlib
import json

from .models import ProcurementNotice
from .models_analysis import AnalysisContextSnapshot
from .opportunity_types import HUMAN_SOURCE


def get_active_context() -> AnalysisContextSnapshot | None:
    return (
        AnalysisContextSnapshot.objects.filter(status=AnalysisContextSnapshot.Status.ACTIVE)
        .order_by("-version")
        .first()
    )


def notice_basis_payload(notice: ProcurementNotice) -> dict:
    prefetched = getattr(notice, "_prefetched_objects_cache", {}).get("source_links")
    if prefetched is not None:
        source_hashes = sorted(
            link.source_notice.content_hash
            for link in prefetched
            if getattr(link, "source_notice", None) is not None
        )
    else:
        source_hashes = sorted(
            notice.source_links.select_related("source_notice")
            .values_list("source_notice__content_hash", flat=True)
        )
    return {
        "id": str(notice.id),
        "type": notice.resolved_notice_type,
        "type_status": notice.type_resolution_status,
        "title": notice.title,
        "summary": notice.summary,
        "description": notice.description,
        "conditions": notice.conditions,
        "employer": notice.employer_name,
        "notice_number": notice.notice_number,
        "province": notice.province,
        "city": notice.city,
        "execution_location": notice.execution_location,
        "published_date": notice.published_date.isoformat() if notice.published_date else None,
        "submission_deadline": notice.submission_deadline.isoformat() if notice.submission_deadline else None,
        "estimated_amount_rials": str(notice.estimated_amount_rials) if notice.estimated_amount_rials is not None else None,
        "guarantee_amount_rials": str(notice.guarantee_amount_rials) if notice.guarantee_amount_rials is not None else None,
        "qualification_text": notice.qualification_text,
        "human_business_opportunity_type": (
            notice.business_opportunity_type
            if notice.business_opportunity_type_source == HUMAN_SOURCE
            else None
        ),
        "source_hashes": source_hashes,
    }


def notice_basis_hash(notice: ProcurementNotice) -> str:
    encoded = json.dumps(
        notice_basis_payload(notice),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
