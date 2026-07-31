from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from . import procurement_analysis_bridge_v6 as base
from .models import AuditEvent, Contract


OPPORTUNITY_ACCEPTANCE_ID = "opportunity-workflow-acceptance-v1-20260731"
OPPORTUNITY_PREFLIGHT_COMMAND = "PDP::OPPORTUNITY_WORKFLOW_ACCEPTANCE::PREFLIGHT"
OPPORTUNITY_START_COMMAND = "PDP::OPPORTUNITY_WORKFLOW_ACCEPTANCE::START"
OPPORTUNITY_ADVANCE_COMMAND = "PDP::OPPORTUNITY_WORKFLOW_ACCEPTANCE::ADVANCE"
OPPORTUNITY_CONVERT_COMMAND = "PDP::OPPORTUNITY_WORKFLOW_ACCEPTANCE::CONVERT"
OPPORTUNITY_STATUS_COMMAND = "PDP::OPPORTUNITY_WORKFLOW_ACCEPTANCE::STATUS"
OPPORTUNITY_COMMANDS = {
    OPPORTUNITY_PREFLIGHT_COMMAND,
    OPPORTUNITY_START_COMMAND,
    OPPORTUNITY_ADVANCE_COMMAND,
    OPPORTUNITY_CONVERT_COMMAND,
    OPPORTUNITY_STATUS_COMMAND,
}


def _workflow_response(operation, **payload):
    return Response(
        {
            "operation": operation,
            "acceptance_id": OPPORTUNITY_ACCEPTANCE_ID,
            **payload,
            "trial_record": True,
            "contract_is_draft": True,
            "requires_human_review": True,
        }
    )


def _load_opportunity(payload):
    from procurement.models_direct import DirectOpportunity

    opportunity_id = str(payload.get("opportunity_id", "")).strip()
    try:
        opportunity = DirectOpportunity.objects.select_related("result", "result__contract").get(
            pk=opportunity_id,
            source_text__startswith=f"{OPPORTUNITY_ACCEPTANCE_ID}:",
            soft_deleted_at__isnull=True,
        )
    except (DirectOpportunity.DoesNotExist, ValueError):
        return None, Response(
            {"detail": "The guarded trial opportunity was not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return opportunity, None


def _serialize_opportunity(opportunity):
    reference_code = ""
    try:
        reference_code = opportunity.reference_record.code
    except Exception:
        reference_code = ""
    result = None
    try:
        result_obj = opportunity.result
        result = {
            "id": str(result_obj.id),
            "outcome": result_obj.outcome,
            "result_date": result_obj.result_date,
            "reason": result_obj.reason,
            "contract_id": str(result_obj.contract_id or ""),
        }
    except Exception:
        result = None
    return {
        "id": str(opportunity.id),
        "reference_code": reference_code,
        "title": opportunity.title,
        "employer_name": opportunity.employer_name,
        "stage": opportunity.stage,
        "next_action": opportunity.next_action,
        "next_action_due": opportunity.next_action_due,
        "source_text": opportunity.source_text,
        "result": result,
    }


def _preflight(request, payload):
    from procurement.models_analysis import NoticeAnalysisDraft
    from procurement.models_direct import DirectOpportunity

    recommended = NoticeAnalysisDraft.objects.filter(
        review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
        is_recommended=True,
    ).order_by("-analyzed_at")
    trial_opportunities = DirectOpportunity.objects.filter(
        source_text__startswith=f"{OPPORTUNITY_ACCEPTANCE_ID}:",
        soft_deleted_at__isnull=True,
    )
    return _workflow_response(
        "preflight",
        ready=recommended.exists(),
        recommended_ai_draft_count=recommended.count(),
        trial_opportunity_count=trial_opportunities.count(),
        requested_draft_id=str(payload.get("analysis_draft_id", "")),
    )


@transaction.atomic
def _start(request, payload):
    from procurement.models_analysis import NoticeAnalysisDraft
    from procurement.models_direct import DirectOpportunity

    if payload.get("acceptance_id") not in {None, "", OPPORTUNITY_ACCEPTANCE_ID}:
        return Response({"detail": "Opportunity acceptance identifier does not match."}, status=409)
    draft_id = str(payload.get("analysis_draft_id", "")).strip()
    try:
        draft = NoticeAnalysisDraft.objects.select_related("notice").get(
            pk=draft_id,
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
            is_recommended=True,
        )
    except (NoticeAnalysisDraft.DoesNotExist, ValueError):
        return Response(
            {"detail": "A recommended AI draft was not found for the guarded trial."},
            status=status.HTTP_404_NOT_FOUND,
        )

    source_text = f"{OPPORTUNITY_ACCEPTANCE_ID}:analysis-draft:{draft.id}:notice:{draft.notice_id}"
    opportunity, created = DirectOpportunity.objects.get_or_create(
        source_text=source_text,
        defaults={
            "title": f"[آزمایشی] {draft.notice.title}",
            "employer_name": draft.notice.employer_name or "کارفرمای درج‌نشده",
            "opportunity_type": DirectOpportunity.OpportunityType.BUSINESS_DEVELOPMENT,
            "stage": DirectOpportunity.Stage.SELECTED,
            "responsible": request.user,
            "next_action": "بازبینی انسانی اسناد و آماده‌سازی پیشنهاد آزمایشی",
            "next_action_due": timezone.now() + timedelta(days=1),
            "description": (
                "رکورد آزمایشی پذیرش جریان انتخاب تا قرارداد؛ تصمیم تجاری نهایی نیست.\n"
                f"AI draft: {draft.id}\nNotice: {draft.notice_id}\nReason: {draft.reason}"
            ),
            "domain": draft.category,
            "province": draft.notice.province,
            "probability": DirectOpportunity.Probability.MEDIUM,
            "probability_percent": min(max(int(draft.score or 0), 0), 100),
            "importance": DirectOpportunity.Importance.LOW,
            "confidentiality": DirectOpportunity.Confidentiality.INTERNAL,
            "created_by": request.user,
        },
    )
    if not created and opportunity.stage not in {
        DirectOpportunity.Stage.SELECTED,
        DirectOpportunity.Stage.PREPARING,
        DirectOpportunity.Stage.SUBMITTED,
        DirectOpportunity.Stage.WON,
        DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
    }:
        return Response({"detail": "Existing trial opportunity is in an incompatible stage."}, status=409)

    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.opportunity_acceptance.start",
        target_type="direct_opportunity",
        target_id=str(opportunity.id),
        payload={
            "acceptance_id": OPPORTUNITY_ACCEPTANCE_ID,
            "analysis_draft_id": str(draft.id),
            "notice_id": str(draft.notice_id),
            "created": created,
            "trial_record": True,
        },
    )
    return _workflow_response(
        "start",
        created=created,
        analysis_draft_id=str(draft.id),
        notice_id=str(draft.notice_id),
        opportunity=_serialize_opportunity(opportunity),
    )


@transaction.atomic
def _advance(request, payload):
    from procurement.models_direct import DirectOpportunity

    opportunity, error = _load_opportunity(payload)
    if error is not None:
        return error
    target_stage = str(payload.get("stage", "")).strip()
    transitions = {
        DirectOpportunity.Stage.SELECTED: {DirectOpportunity.Stage.PREPARING},
        DirectOpportunity.Stage.PREPARING: {DirectOpportunity.Stage.SUBMITTED},
        DirectOpportunity.Stage.SUBMITTED: {DirectOpportunity.Stage.WON},
        DirectOpportunity.Stage.WON: set(),
        DirectOpportunity.Stage.CONVERTED_TO_CONTRACT: set(),
    }
    if target_stage not in transitions.get(opportunity.stage, set()):
        return Response(
            {"detail": f"Invalid guarded trial transition: {opportunity.stage} -> {target_stage}."},
            status=status.HTTP_409_CONFLICT,
        )
    next_action_by_stage = {
        DirectOpportunity.Stage.PREPARING: "تهیه پیشنهاد آزمایشی و کنترل مدارک",
        DirectOpportunity.Stage.SUBMITTED: "ثبت نتیجه ارسال آزمایشی",
        DirectOpportunity.Stage.WON: "تبدیل نتیجه آزمایشی به قرارداد پیش‌نویس",
    }
    before = opportunity.stage
    opportunity.stage = target_stage
    opportunity.next_action = next_action_by_stage[target_stage]
    opportunity.next_action_due = timezone.now() + timedelta(days=1)
    opportunity.last_activity_at = timezone.now()
    opportunity.save(update_fields=["stage", "next_action", "next_action_due", "last_activity_at", "updated_at"])
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.opportunity_acceptance.advance",
        target_type="direct_opportunity",
        target_id=str(opportunity.id),
        payload={
            "acceptance_id": OPPORTUNITY_ACCEPTANCE_ID,
            "stage_before": before,
            "stage_after": target_stage,
            "trial_record": True,
        },
    )
    return _workflow_response("advance", opportunity=_serialize_opportunity(opportunity))


@transaction.atomic
def _convert(request, payload):
    from procurement.models_direct import DirectOpportunity, OpportunityResult

    opportunity, error = _load_opportunity(payload)
    if error is not None:
        return error
    if opportunity.stage == DirectOpportunity.Stage.CONVERTED_TO_CONTRACT:
        return _workflow_response(
            "convert",
            created=False,
            opportunity=_serialize_opportunity(opportunity),
            contract={
                "id": str(opportunity.result.contract_id),
                "code": opportunity.result.contract.code,
                "status": opportunity.result.contract.status,
            },
        )
    if opportunity.stage != DirectOpportunity.Stage.WON:
        return Response(
            {"detail": "The guarded trial opportunity must be in won stage before conversion."},
            status=status.HTTP_409_CONFLICT,
        )

    contract_code = f"TRIAL-{str(opportunity.id).replace('-', '')[:10].upper()}"
    contract, _ = Contract.objects.get_or_create(
        code=contract_code,
        defaults={
            "title": opportunity.title,
            "employer": opportunity.employer_name,
            "field": opportunity.domain,
            "value_rials": opportunity.estimated_value_rials,
            "progress": 0,
            "status": Contract.Status.DRAFT,
            "created_by": request.user,
        },
    )
    result, created = OpportunityResult.objects.get_or_create(
        opportunity=opportunity,
        defaults={
            "outcome": OpportunityResult.Outcome.CONVERTED_TO_CONTRACT,
            "result_date": timezone.localdate(),
            "reason": "پذیرش آزمایشی جریان نتیجه تا قرارداد پیش‌نویس",
            "notes": "این نتیجه آزمایشی است و تصمیم تجاری یا قرارداد نهایی محسوب نمی‌شود.",
            "contract": contract,
            "created_by": request.user,
        },
    )
    if not created and result.contract_id != contract.id:
        return Response({"detail": "Existing trial result points to a different contract."}, status=409)
    opportunity.stage = DirectOpportunity.Stage.CONVERTED_TO_CONTRACT
    opportunity.next_action = "بازبینی انسانی قرارداد پیش‌نویس آزمایشی"
    opportunity.next_action_due = timezone.now() + timedelta(days=1)
    opportunity.last_activity_at = timezone.now()
    opportunity.save(update_fields=["stage", "next_action", "next_action_due", "last_activity_at", "updated_at"])
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.opportunity_acceptance.convert_to_contract_draft",
        target_type="direct_opportunity",
        target_id=str(opportunity.id),
        payload={
            "acceptance_id": OPPORTUNITY_ACCEPTANCE_ID,
            "result_id": str(result.id),
            "contract_id": str(contract.id),
            "contract_code": contract.code,
            "contract_status": contract.status,
            "trial_record": True,
        },
    )
    return _workflow_response(
        "convert",
        created=created,
        opportunity=_serialize_opportunity(opportunity),
        contract={
            "id": str(contract.id),
            "code": contract.code,
            "title": contract.title,
            "employer": contract.employer,
            "status": contract.status,
        },
    )


def _status(request, payload):
    opportunity, error = _load_opportunity(payload)
    if error is not None:
        return error
    return _workflow_response("status", opportunity=_serialize_opportunity(opportunity))


def handle_procurement_analysis_command(request):
    title = str(request.data.get("title", "")).strip()
    if title not in OPPORTUNITY_COMMANDS:
        return base.handle_procurement_analysis_command(request)
    if not base.v2._allowed(request.user):
        return Response(
            {"detail": "Guarded opportunity acceptance commands are limited to administrators and ChatGPT service account."},
            status=status.HTTP_403_FORBIDDEN,
        )
    payload, error = base.v2._parse_payload(request)
    if error is not None:
        return error
    if title == OPPORTUNITY_PREFLIGHT_COMMAND:
        return _preflight(request, payload)
    if title == OPPORTUNITY_START_COMMAND:
        return _start(request, payload)
    if title == OPPORTUNITY_ADVANCE_COMMAND:
        return _advance(request, payload)
    if title == OPPORTUNITY_CONVERT_COMMAND:
        return _convert(request, payload)
    return _status(request, payload)
