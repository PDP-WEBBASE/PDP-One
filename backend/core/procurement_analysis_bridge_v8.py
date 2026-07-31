from . import procurement_analysis_bridge_v7 as base


ACCEPTANCE_ID = base.ACCEPTANCE_ID
PREFLIGHT_COMMAND = base.PREFLIGHT_COMMAND
START_COMMAND = base.START_COMMAND
SAVE_COMMAND = base.SAVE_COMMAND
FINISH_COMMAND = base.FINISH_COMMAND
RESERVED_COMMANDS = base.RESERVED_COMMANDS

OPPORTUNITY_ACCEPTANCE_ID = base.OPPORTUNITY_ACCEPTANCE_ID
OPPORTUNITY_PREFLIGHT_COMMAND = base.OPPORTUNITY_PREFLIGHT_COMMAND
OPPORTUNITY_START_COMMAND = base.OPPORTUNITY_START_COMMAND
OPPORTUNITY_ADVANCE_COMMAND = base.OPPORTUNITY_ADVANCE_COMMAND
OPPORTUNITY_CONVERT_COMMAND = base.OPPORTUNITY_CONVERT_COMMAND
OPPORTUNITY_STATUS_COMMAND = base.OPPORTUNITY_STATUS_COMMAND
OPPORTUNITY_COMMANDS = base.OPPORTUNITY_COMMANDS


def handle_procurement_analysis_command(request):
    response = base.handle_procurement_analysis_command(request)
    title = str(request.data.get("title", "")).strip()
    if title != OPPORTUNITY_PREFLIGHT_COMMAND or response.status_code >= 400:
        return response

    from procurement.models_analysis import NoticeAnalysisDraft

    drafts = (
        NoticeAnalysisDraft.objects.filter(
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
            is_recommended=True,
        )
        .select_related("notice")
        .order_by("-analyzed_at")[:10]
    )
    response.data["recommended_ai_drafts"] = [
        {
            "id": str(draft.id),
            "notice_id": str(draft.notice_id),
            "title": draft.notice.title,
            "employer_name": draft.notice.employer_name,
            "category": draft.category,
            "score": draft.score,
            "priority": draft.priority,
            "reason": draft.reason,
            "analyzed_at": draft.analyzed_at,
            "review_status": draft.review_status,
        }
        for draft in drafts
    ]
    return response
