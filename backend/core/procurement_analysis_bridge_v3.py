from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from . import procurement_analysis_bridge_v2 as v2
from .models import AuditEvent


PREFLIGHT_COMMAND = v2.PREFLIGHT_COMMAND
START_COMMAND = v2.START_COMMAND
SAVE_COMMAND = v2.SAVE_COMMAND
FINISH_COMMAND = v2.FINISH_COMMAND
RESERVED_COMMANDS = v2.RESERVED_COMMANDS
ACCEPTANCE_ID = v2.ACCEPTANCE_ID


def _failed(stage: str, exc: Exception):
    return Response(
        {
            "detail": f"Guarded procurement-analysis start failed safely; stage={stage}; error={exc.__class__.__name__}.",
            "operation": "start",
            "stage": stage,
            "safe_error": exc.__class__.__name__,
            "acceptance_id": ACCEPTANCE_ID,
            "decision_is_draft": True,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@transaction.atomic
def _start(request, payload):
    from procurement.analysis_utils import get_active_context
    from procurement.analysis_workflow import normalize_limit, serialize_work, start_analysis_request
    from procurement.models_analysis import AnalysisRequest
    from procurement.models_extraction import ExtractionRun
    from procurement.serializers_analysis import AnalysisBatchSerializer, AnalysisRequestSerializer

    try:
        active = get_active_context()
    except Exception as exc:
        return _failed("active-context", exc)
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
        except Exception as exc:
            return _failed("load-extraction", exc)
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
    try:
        recovered = v2._recover_open_acceptance_requests(request.user.username)
    except Exception as exc:
        return _failed("recover-open-requests", exc)

    try:
        analysis_request = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_CHATGPT,
            command="PDP",
            status=AnalysisRequest.Status.PENDING,
            extraction_run=extraction_run,
            context_snapshot=active,
            requested_by=request.user,
            metadata={
                "acceptance_id": ACCEPTANCE_ID,
                "bridge": "analysis-report-reserved-command-v3",
                "requested_limit": limit,
                "recovered_request_ids": recovered,
            },
        )
    except Exception as exc:
        return _failed("create-request", exc)

    try:
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.analysis_acceptance.create",
            target_type="analysis_request",
            target_id=str(analysis_request.id),
            payload={"acceptance_id": ACCEPTANCE_ID, "limit": limit, "recovered_count": len(recovered)},
        )
    except Exception as exc:
        return _failed("audit-create", exc)

    try:
        analysis_request, batch = start_analysis_request(
            analysis_request,
            limit=limit,
            actor=request.user.username,
        )
    except Exception as exc:
        return _failed("start-workflow", exc)

    try:
        work = serialize_work(analysis_request, limit=limit) if batch else []
    except Exception as exc:
        return _failed("serialize-work", exc)

    try:
        response_payload = {
            "operation": "start",
            "acceptance_id": ACCEPTANCE_ID,
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data if batch else None,
            "context": v2._compact_context(active),
            "count": len(work),
            "items": work,
            "recovered_request_ids": recovered,
            "decision_is_draft": True,
            "requires_human_review": True,
        }
    except Exception as exc:
        return _failed("serialize-response", exc)
    return Response(response_payload, status=status.HTTP_201_CREATED)


def handle_procurement_analysis_command(request):
    title = str(request.data.get("title", "")).strip()
    if title != START_COMMAND:
        return v2.handle_procurement_analysis_command(request)
    if not v2._allowed(request.user):
        return Response(
            {"detail": "Reserved procurement-analysis commands are limited to administrators and the ChatGPT service account."},
            status=status.HTTP_403_FORBIDDEN,
        )
    payload, error = v2._parse_payload(request)
    if error is not None:
        return error
    return _start(request, payload)
