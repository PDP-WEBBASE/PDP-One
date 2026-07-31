import json

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from .models import AuditEvent


PREFLIGHT_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::PREFLIGHT"
START_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::START"
SAVE_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::SAVE"
FINISH_COMMAND = "PDP::PROCUREMENT_ANALYSIS_ACCEPTANCE::FINISH"
RESERVED_COMMANDS = {PREFLIGHT_COMMAND, START_COMMAND, SAVE_COMMAND, FINISH_COMMAND}
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


def _compact_context(context):
    return {
        "id": str(context.id),
        "version": context.version,
        "status": context.status,
        "content_hash": context.content_hash,
        "component_versions": context.component_versions,
        "changed_components": context.changed_components,
    }


def _preflight(request, payload):
    from procurement.analysis_utils import get_active_context
    from procurement.models import ProcurementNotice
    from procurement.models_analysis import AnalysisRequest, NoticeAnalysisDraft
    from procurement.models_extraction import ExtractionRun

    active = get_active_context()
    latest_run = (
        ExtractionRun.objects.filter(
            status__in=[
                ExtractionRun.Status.SUCCEEDED,
                ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
                ExtractionRun.Status.PARTIAL,
            ]
        )
        .order_by("-finished_at", "-created_at")
        .first()
    )
    open_requests = AnalysisRequest.objects.filter(
        metadata__acceptance_id=ACCEPTANCE_ID,
        status__in=[AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING],
    ).count()
    return Response(
        {
            "operation": "preflight",
            "acceptance_id": ACCEPTANCE_ID,
            "ready": active is not None,
            "context": _compact_context(active) if active else None,
            "latest_extraction": {
                "id": str(latest_run.id),
                "status": latest_run.status,
                "finished_at": latest_run.finished_at,
            }
            if latest_run
            else None,
            "notice_count": ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False).count(),
            "existing_ai_drafts": NoticeAnalysisDraft.objects.filter(review_status="ai_draft").count(),
            "open_acceptance_requests": open_requests,
            "requested_limit": payload.get("limit"),
            "decision_is_draft": True,
            "requires_human_review": True,
        }
    )


def _recover_open_acceptance_requests(actor: str):
    from procurement.models import ProcurementNotice
    from procurement.models_analysis import AnalysisBatch, AnalysisRequest, NoticeAnalysisDraft

    recovered = []
    requests = list(
        AnalysisRequest.objects.select_for_update()
        .filter(
            metadata__acceptance_id=ACCEPTANCE_ID,
            status__in=[AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING],
        )
        .order_by("created_at")
    )
    for analysis_request in requests:
        candidate_ids = [str(value) for value in (analysis_request.metadata or {}).get("candidate_notice_ids", [])]
        drafted_ids = set(
            str(value)
            for value in NoticeAnalysisDraft.objects.filter(batch__request=analysis_request).values_list("notice_id", flat=True)
        )
        reset_ids = [notice_id for notice_id in candidate_ids if notice_id not in drafted_ids]
        if reset_ids:
            ProcurementNotice.objects.filter(
                id__in=reset_ids,
                processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_QUEUED,
            ).update(processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS)
        now = timezone.now()
        analysis_request.batches.filter(status__in=[AnalysisBatch.Status.OPEN, AnalysisBatch.Status.PROCESSING]).update(
            status=AnalysisBatch.Status.FAILED,
            failed_count=len(reset_ids),
            finished_at=now,
            summary={
                "acceptance_id": ACCEPTANCE_ID,
                "recovered": True,
                "reason": "Superseded incomplete acceptance request.",
                "reset_notice_ids": reset_ids,
            },
        )
        analysis_request.status = AnalysisRequest.Status.FAILED
        analysis_request.completed_at = now
        analysis_request.last_error = "Incomplete acceptance request recovered before retry."
        analysis_request.metadata = {
            **(analysis_request.metadata or {}),
            "recovered": True,
            "recovered_at": now.isoformat(),
            "reset_notice_ids": reset_ids,
        }
        analysis_request.save(update_fields=["status", "completed_at", "last_error", "metadata", "updated_at"])
        recovered.append(str(analysis_request.id))
        AuditEvent.objects.create(
            actor=actor,
            action="procurement.analysis_acceptance.recover",
            target_type="analysis_request",
            target_id=str(analysis_request.id),
            payload={"acceptance_id": ACCEPTANCE_ID, "reset_count": len(reset_ids)},
        )
    return recovered


@transaction.atomic
def _start(request, payload):
    from procurement.analysis_utils import get_active_context
    from procurement.analysis_workflow import normalize_limit, serialize_work, start_analysis_request
    from procurement.models_analysis import AnalysisRequest
    from procurement.models_extraction import ExtractionRun
    from procurement.serializers_analysis import AnalysisBatchSerializer, AnalysisRequestSerializer

    active = get_active_context()
    if active is None:
        return Response(
            {"detail": "No active procurement analysis context is configured.", "operation": "start"},
            status=status.HTTP_409_CONFLICT,
        )

    extraction_run = None
    extraction_run_id = str(payload.get("extraction_run") or "").strip()
    if extraction_run_id:
        try:
            extraction_run = ExtractionRun.objects.get(pk=extraction_run_id)
        except (ExtractionRun.DoesNotExist, ValueError):
            return Response({"detail": "Extraction run was not found."}, status=status.HTTP_404_NOT_FOUND)
        if extraction_run.status not in {
            ExtractionRun.Status.SUCCEEDED,
            ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
            ExtractionRun.Status.PARTIAL,
        }:
            return Response(
                {"detail": "Extraction run is not in an analyzable terminal status."},
                status=status.HTTP_409_CONFLICT,
            )

    limit = normalize_limit(payload.get("limit"), default=5)
    recovered = _recover_open_acceptance_requests(request.user.username)
    analysis_request = AnalysisRequest.objects.create(
        trigger=AnalysisRequest.Trigger.MANUAL_CHATGPT,
        command="PDP",
        status=AnalysisRequest.Status.PENDING,
        extraction_run=extraction_run,
        context_snapshot=active,
        requested_by=request.user,
        metadata={
            "acceptance_id": ACCEPTANCE_ID,
            "bridge": "analysis-report-reserved-command-v2",
            "requested_limit": limit,
            "recovered_request_ids": recovered,
        },
    )
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.analysis_acceptance.create",
        target_type="analysis_request",
        target_id=str(analysis_request.id),
        payload={"acceptance_id": ACCEPTANCE_ID, "limit": limit, "recovered_count": len(recovered)},
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
            "context": _compact_context(active),
            "count": len(work),
            "items": work,
            "recovered_request_ids": recovered,
            "decision_is_draft": True,
            "requires_human_review": True,
        },
        status=status.HTTP_201_CREATED,
    )


@transaction.atomic
def _save(request, payload):
    from procurement.models_analysis import AnalysisBatch
    from procurement.serializers_analysis import NoticeAnalysisDraftSerializer

    if payload.get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The procurement-analysis acceptance identifier does not match."},
            status=status.HTTP_409_CONFLICT,
        )

    request_id = str(payload.get("request_id", "")).strip()
    batch_id = str(payload.get("batch_id", "")).strip()
    notice_id = str(payload.get("notice_id", "")).strip()
    try:
        batch = AnalysisBatch.objects.select_related("request", "context_snapshot").get(pk=batch_id)
    except (AnalysisBatch.DoesNotExist, ValueError):
        return Response({"detail": "Analysis batch was not found."}, status=status.HTTP_404_NOT_FOUND)

    request_acceptance_id = (batch.request.metadata or {}).get("acceptance_id")
    candidate_ids = [str(value) for value in (batch.request.metadata or {}).get("candidate_notice_ids", [])]
    if (
        request_acceptance_id != ACCEPTANCE_ID
        or str(batch.request_id) != request_id
        or notice_id not in candidate_ids
    ):
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
                "engine": "ChatGPT connected app acceptance bridge v2",
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


@transaction.atomic
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
            "engine": "ChatGPT connected app acceptance bridge v2",
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
    try:
        if title == PREFLIGHT_COMMAND:
            return _preflight(request, payload)
        if title == START_COMMAND:
            return _start(request, payload)
        if title == SAVE_COMMAND:
            return _save(request, payload)
        return _finish(request, payload)
    except Exception as exc:
        operation = title.rsplit("::", 1)[-1].lower()
        return Response(
            {
                "detail": "The guarded procurement-analysis command failed safely.",
                "operation": operation,
                "safe_error": exc.__class__.__name__,
                "acceptance_id": ACCEPTANCE_ID,
                "decision_is_draft": True,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
