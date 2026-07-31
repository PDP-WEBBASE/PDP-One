from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from . import procurement_analysis_bridge_v2 as v2
from . import procurement_analysis_bridge_v5 as v5
from .models import AuditEvent


PREFLIGHT_COMMAND = v5.PREFLIGHT_COMMAND
START_COMMAND = v5.START_COMMAND
SAVE_COMMAND = v5.SAVE_COMMAND
FINISH_COMMAND = v5.FINISH_COMMAND
RESERVED_COMMANDS = v5.RESERVED_COMMANDS
ACCEPTANCE_ID = v5.ACCEPTANCE_ID


def _finish_failed(stage: str, exc: Exception):
    if transaction.get_connection().in_atomic_block:
        transaction.set_rollback(True)
    return Response(
        {
            "detail": f"Guarded procurement-analysis finish failed safely; stage={stage}; error={exc.__class__.__name__}.",
            "operation": "finish",
            "stage": stage,
            "safe_error": exc.__class__.__name__,
            "acceptance_id": ACCEPTANCE_ID,
            "decision_is_draft": True,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@transaction.atomic
def _finish(request, payload):
    from procurement.models import ProcurementNotice
    from procurement.models_analysis import AnalysisBatch, AnalysisRequest, NoticeAnalysisDraft
    from procurement.serializers_analysis import AnalysisBatchSerializer, AnalysisRequestSerializer

    if payload.get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The procurement-analysis acceptance identifier does not match."},
            status=status.HTTP_409_CONFLICT,
        )

    request_id = str(payload.get("request_id", "")).strip()
    try:
        analysis_request = AnalysisRequest.objects.get(pk=request_id)
    except (AnalysisRequest.DoesNotExist, ValueError):
        return Response({"detail": "Analysis request was not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return _finish_failed("load-request", exc)

    if (analysis_request.metadata or {}).get("acceptance_id") != ACCEPTANCE_ID:
        return Response(
            {"detail": "The request is not part of the guarded acceptance run."},
            status=status.HTTP_409_CONFLICT,
        )
    if analysis_request.status not in {AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING}:
        return Response(
            {"detail": "The guarded acceptance request is not open.", "status": analysis_request.status},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        batch = analysis_request.batches.order_by("-sequence").first()
    except Exception as exc:
        return _finish_failed("load-batch", exc)
    if batch is None:
        return Response(
            {"detail": "No active analysis batch exists for this request."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        candidate_ids = [str(value) for value in (analysis_request.metadata or {}).get("candidate_notice_ids", [])]
        supplied_failed = {
            str(value)
            for value in (payload.get("failed_notice_ids") or [])
            if str(value) in candidate_ids
        }
        drafted_ids = {
            str(value)
            for value in NoticeAnalysisDraft.objects.filter(batch=batch).values_list("notice_id", flat=True)
        }
        unresolved_ids = set(candidate_ids) - drafted_ids
        failed_ids = supplied_failed | unresolved_ids
        completed_count = len(drafted_ids)
        failed_count = len(failed_ids)
    except Exception as exc:
        return _finish_failed("calculate-result", exc)

    if completed_count and failed_count:
        batch_status = AnalysisBatch.Status.PARTIAL
        request_status = AnalysisRequest.Status.COMPLETED
    elif failed_count:
        batch_status = AnalysisBatch.Status.FAILED
        request_status = AnalysisRequest.Status.FAILED
    elif completed_count:
        batch_status = AnalysisBatch.Status.COMPLETED
        request_status = AnalysisRequest.Status.COMPLETED
    else:
        batch_status = AnalysisBatch.Status.COMPLETED
        request_status = AnalysisRequest.Status.NO_CHANGES

    now = timezone.now()
    try:
        batch.status = batch_status
        batch.completed_count = completed_count
        batch.failed_count = failed_count
        batch.finished_at = now
        batch.summary = {
            **(batch.summary or {}),
            "acceptance_id": ACCEPTANCE_ID,
            "note": str(payload.get("summary_note", ""))[:1000],
            "engine": "ChatGPT connected app acceptance bridge v6",
            "completed_count": completed_count,
            "failed_count": failed_count,
            "failed_notice_ids": sorted(failed_ids),
            "locking_mode": "transaction-atomic-no-row-lock",
        }
        batch.save(
            update_fields=[
                "status",
                "completed_count",
                "failed_count",
                "finished_at",
                "summary",
                "updated_at",
            ]
        )
        if failed_ids:
            ProcurementNotice.objects.filter(id__in=failed_ids).update(
                processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_FAILED
            )

        analysis_request.status = request_status
        analysis_request.completed_at = now
        analysis_request.last_error = (
            "" if request_status != AnalysisRequest.Status.FAILED else "Analysis completed with no successful drafts."
        )
        analysis_request.metadata = {
            **(analysis_request.metadata or {}),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "failed_notice_ids": sorted(failed_ids),
            "finished_by_bridge": "v6",
        }
        analysis_request.save(
            update_fields=["status", "completed_at", "last_error", "metadata", "updated_at"]
        )
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.analysis_acceptance.finish",
            target_type="analysis_request",
            target_id=str(analysis_request.id),
            payload={
                "acceptance_id": ACCEPTANCE_ID,
                "batch_id": str(batch.id),
                "status": request_status,
                "completed_count": completed_count,
                "failed_count": failed_count,
                "locking_mode": "transaction-atomic-no-row-lock",
            },
        )
    except Exception as exc:
        return _finish_failed("persist-result", exc)

    try:
        response_payload = {
            "operation": "finish",
            "acceptance_id": ACCEPTANCE_ID,
            "request": AnalysisRequestSerializer(analysis_request).data,
            "batch": AnalysisBatchSerializer(batch).data,
            "decision_is_draft": True,
            "requires_human_review": True,
        }
    except Exception as exc:
        return _finish_failed("serialize-response", exc)
    return Response(response_payload)


def handle_procurement_analysis_command(request):
    title = str(request.data.get("title", "")).strip()
    if title != FINISH_COMMAND:
        return v5.handle_procurement_analysis_command(request)
    if not v2._allowed(request.user):
        return Response(
            {"detail": "Reserved procurement-analysis commands are limited to administrators and the ChatGPT service account."},
            status=status.HTTP_403_FORBIDDEN,
        )
    payload, error = v2._parse_payload(request)
    if error is not None:
        return error
    return _finish(request, payload)
