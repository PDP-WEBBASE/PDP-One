from __future__ import annotations

from typing import Any

from .models_analysis import NoticeAnalysisDraft


def human_review_metadata(draft: NoticeAnalysisDraft) -> dict[str, Any]:
    raw_output = draft.raw_output if isinstance(draft.raw_output, dict) else {}
    metadata = raw_output.get("human_review")
    return metadata if isinstance(metadata, dict) else {}


def analysis_review_summary(queryset=None) -> dict[str, Any]:
    source = queryset if queryset is not None else NoticeAnalysisDraft.objects.all()
    drafts = list(
        source.only(
            "review_status",
            "priority",
            "is_recommended",
            "raw_output",
        )
    )
    counters = {
        "total": len(drafts),
        "pending_review": 0,
        "needs_revision": 0,
        "reviewed": 0,
        "published": 0,
        "rejected": 0,
        "recommended": 0,
        "urgent": 0,
    }
    by_status: dict[str, int] = {}

    for draft in drafts:
        by_status[draft.review_status] = by_status.get(draft.review_status, 0) + 1
        metadata = human_review_metadata(draft)
        needs_revision = (
            draft.review_status == NoticeAnalysisDraft.ReviewStatus.AI_DRAFT
            and metadata.get("decision") == "needs_revision"
        )
        if needs_revision:
            counters["needs_revision"] += 1
        elif draft.review_status == NoticeAnalysisDraft.ReviewStatus.AI_DRAFT:
            counters["pending_review"] += 1
        elif draft.review_status == NoticeAnalysisDraft.ReviewStatus.REVIEWED:
            counters["reviewed"] += 1
        elif draft.review_status == NoticeAnalysisDraft.ReviewStatus.PUBLISHED:
            counters["published"] += 1
        elif draft.review_status == NoticeAnalysisDraft.ReviewStatus.REJECTED:
            counters["rejected"] += 1

        if draft.is_recommended:
            counters["recommended"] += 1
        if draft.priority == NoticeAnalysisDraft.Priority.URGENT:
            counters["urgent"] += 1

    return {**counters, "by_status": by_status}
