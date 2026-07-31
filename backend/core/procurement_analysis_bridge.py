import json

from rest_framework import status
from rest_framework.response import Response

from .models import AuditEvent


START_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::START"
SAVE_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::SAVE"
FINISH_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::FINISH"
RESERVED_COMMANDS = {START_COMMAND, SAVE_COMMAND, FINISH_COMMAND}
ACCEPTANCE_ID = "analysis-engine-acceptance-v1-20260731"


def _allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


def _parse_payload(request):
    raw = request.data.get("summary", "")
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return None, Response(
            {"detail": "Reserved procurement-analysis commands require a JSON object in summary."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(payload, dict):
        return None, Response(
            {"detail": "Reserved procurement-analysis command payload must be a JSON object."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return payload, None


def _start(request, payload):
    from procurement.analysis_workflow import normalize_limit, serialize_work, start_analysis_request
    from procurement.models_analysis import AnalysisRequest
    from procurement.serializers_analysis import (
        AnalysisBatchSerializer,
        AnalysisContextSnapshotSerializer,
        AnalysisRequestSerializer,
    )

    limit = normalize_limit(payload.get("limit"), default=5)
    serializer = AnalysisRequestSerializer(
        data={
            "trigger": AnalysisRequest.Trigger.MANUAL_CHATGPT,
            "extraction_run": payload.get("extraction_run"),
            "metadata": {
                "acceptance_id": ACCEPTANCE_ID,
                "bridge": "analysis-report-reserved-command",
                "requested_limit": limit,
            },
        },
        context={"request": request, "allow_scheduled": False},
    )
    serializer.is_valid(raise_exception=True)
    analysis_request = serializer.save()
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.analysis_acceptance.create",
        target_type="analysis_request",
        target_id=str(analysis_request.id),
        payload={"acceptance_id": ACCEPTANCE_ID, "limit": limit},
    )
    analysis_request, batch = start_analysis_request(
        analysis_request,
        limit=limit,
        actor=request.user.username,
    )
    work = serialize_work(analysis_request, limit=limit) if batch else []
    return Response(
        {
            "operation": "start",
            "acceptance_id": ACCEPTANCE_ID,
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data if batch else None,
            "context": AnalysisContextSnapshotSerializer(analysis_request.context_snapshot).data,
            "count": len(work),
            "items": work,
            "decision_is_draft": True,
            "requires_human_review": True,
        },
        status=status.HTTP_201_CREATED,
    )


def _save(request, payload):
    from procurement.models_analysis import AnalysisBatch
    from procurement.serializers_analysis import NoticeAnalysisDraftSerializer

    if payload.get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The procurement-analysis acceptance identifier does not match."},
            status=status.HTTP_409_CONFLICT,
        )

    batch_id = str(payload.get("batch_id", "")).strip()
    notice_id = str(payload.get("notice_id", "")).strip()
    try:
        batch = AnalysisBatch.objects.select_related("request", "context_snapshot").get(pk=batch_id)
    except (AnalysisBatch.DoesNotExist, ValueError):
        return Response({"detail": "Analysis batch was not found."}, status=status.HTTP_404_NOT_FOUND)

    request_acceptance_id = (batch.request.metadata or {}).get("acceptance_id")
    candidate_ids = [str(value) for value in (batch.request.metadata or {}).get("candidate_notice_ids", [])]
    if request_acceptance_id != ACCEPTANCE_ID or notice_id not in candidate_ids:
        return Response(
            {"detail": "The notice is not part of this guarded acceptance batch."},
            status=status.HTTP_409_CONFLICT,
        )

    supplied_source_ids = [str(value) for value in (request.data.get("source_record_ids") or [])]
    if supplied_source_ids and notice_id not in supplied_source_ids:
        return Response(
            {"detail": "source_record_ids must include the guarded notice id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = NoticeAnalysisDraftSerializer(
        data={
            "notice": notice_id,
            "batch": batch_id,
            "is_recommended": bool(payload.get("is_recommended", False)),
            "score": payload.get("score"),
            "priority": payload.get("priority", "medium"),
            "fit_for_pdp": payload.get("fit_for_pdp", ""),
            "category": payload.get("category", ""),
            "reason": payload.get("reason", ""),
            "recommended_action": payload.get("recommended_action", ""),
            "matched_experience": payload.get("matched_experience") or [],
            "risk_notes": payload.get("risk_notes") or [],
            "confidence": payload.get("confidence"),
            "raw_output": {
                "engine": "ChatGPT connected app acceptance bridge",
                "acceptance_id": ACCEPTANCE_ID,
                "decision_is_draft": True,
            },
        },
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    draft = serializer.save()
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.analysis_acceptance.save_draft",
        target_type="notice_analysis_draft",
        target_id=str(draft.id),
        payload={
            "acceptance_id": ACCEPTANCE_ID,
            "notice_id": notice_id,
            "batch_id": batch_id,
            "recommended": draft.is_recommended,
        },
    )
    return Response(
        {
            "operation": "save",
            "acceptance_id": ACCEPTANCE_ID,
            "draft": NoticeAnalysisDraftSerializer(draft).data,
            "decision_is_draft": True,
            "requires_human_review": True,
        },
        status=status.HTTP_201_CREATED,
    )


def _finish(request, payload):
    from procurement.analysis_workflow import finish_analysis_request
    from procurement.models_analysis import AnalysisRequest
    from procurement.serializers_analysis import AnalysisBatchSerializer, AnalysisRequestSerializer

    if payload.get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The procurement-analysis acceptance identifier does not match."},
            status=status.HTTP_409_CONFLICT,
        )

    request_id = str(payload.get("request_id", "")).strip()
    try:
        analysis_request = AnalysisRequest.objects.select_related("context_snapshot").get(pk=request_id)
    except (AnalysisRequest.DoesNotExist, ValueError):
        return Response({"detail": "Analysis request was not found."}, status=status.HTTP_404_NOT_FOUND)

    if (analysis_request.metadata or {}).get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The request is not part of the guarded acceptance run."},
            status=status.HTTP_409_CONFLICT,
        )

    analysis_request, batch = finish_analysis_request(
        analysis_request,
        actor=request.user.username,
        failed_notice_ids=payload.get("failed_notice_ids") or [],
        summary={
            "acceptance_id": ACCEPTANCE_ID,
            "note": str(payload.get("summary_note", ""))[:1000],
            "engine": "ChatGPT connected app acceptance bridge",
        },
    )
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.analysis_acceptance.finish",
        target_type="analysis_request",
        target_id=str(analysis_request.id),
        payload={
            "acceptance_id": ACCEPTANCE_ID,
            "status": analysis_request.status,
            "completed_count": (batch.completed_count if batch else 0),
            "failed_count": (batch.failed_count if batch else 0),
        },
    )
    return Response(
        {
            "operation": "finish",
            "acceptance_id": ACCEPTANCE_ID,
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data if batch else None,
            "decision_is_draft": True,
            "requires_human_review": True,
        }
    )


def handle_procurement_analysis_command(request):
    title = str(request.data.get("title", "")).strip()
    if title not in RESERVED_COMMANDS:
        return None
    if not _allowed(request.user):
        return Response(
            {"detail": "Reserved procurement-analysis commands are limited to administrators and the ChatGPT service account."},
            status=status.HTTP_403_FORBIDDEN,
        )

    payload, error = _parse_payload(request)
    if error is not None:
        return error
    if title == START_COMMAND:
        return _start(request, payload)
    if title == SAVE_COMMAND:
        return _save(request, payload)
    return _finish(request, payload)
