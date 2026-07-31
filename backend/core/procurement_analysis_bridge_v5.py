from django.db import transaction
from django.utils import timezone
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
    # Returning a Response from an atomic block would normally commit earlier
    # writes. Mark the transaction for rollback so a failed acceptance start
    # never leaves a partial request or batch behind.
    if transaction.get_connection().in_atomic_block:
        transaction.set_rollback(True)
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
    from procurement.analysis_utils import get_active_context, notice_basis_payload
    from procurement.analysis_workflow import collect_work_items, normalize_limit
    from procurement.models import ProcurementNotice
    from procurement.models_analysis import AnalysisBatch, AnalysisRequest
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
                "bridge": "analysis-report-reserved-command-v5",
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
    except Exception as exc:
        return _failed("create-request", exc)

    try:
        work_items = collect_work_items(analysis_request, limit=limit)
    except Exception as exc:
        return _failed("collect-work-items", exc)

    now = timezone.now()
    if not work_items:
        try:
            analysis_request.status = AnalysisRequest.Status.NO_CHANGES
            analysis_request.started_at = now
            analysis_request.completed_at = now
            analysis_request.metadata = {
                **(analysis_request.metadata or {}),
                "candidate_notice_ids": [],
                "candidate_count": 0,
                "context_version": active.version,
                "result": "no_changes",
            }
            analysis_request.save(
                update_fields=["status", "started_at", "completed_at", "metadata", "updated_at"]
            )
            AuditEvent.objects.create(
                actor=request.user.username,
                action="procurement.analysis_request.no_changes",
                target_type="analysis_request",
                target_id=str(analysis_request.id),
                payload={"context_version": active.version, "acceptance_id": ACCEPTANCE_ID},
            )
        except Exception as exc:
            return _failed("complete-no-changes", exc)
        batch = None
        work = []
    else:
        candidate_ids = [str(item.notice.id) for item in work_items]
        try:
            batch = AnalysisBatch.objects.create(
                request=analysis_request,
                context_snapshot=active,
                status=AnalysisBatch.Status.PROCESSING,
                sequence=1,
                item_count=len(work_items),
                started_at=now,
                summary={"candidate_notice_ids": candidate_ids, "acceptance_id": ACCEPTANCE_ID},
            )
            analysis_request.status = AnalysisRequest.Status.PROCESSING
            analysis_request.started_at = now
            analysis_request.metadata = {
                **(analysis_request.metadata or {}),
                "candidate_notice_ids": candidate_ids,
                "candidate_count": len(candidate_ids),
                "batch_id": str(batch.id),
                "context_version": active.version,
            }
            analysis_request.save(update_fields=["status", "started_at", "metadata", "updated_at"])
            ProcurementNotice.objects.filter(id__in=candidate_ids).exclude(
                processing_status=ProcurementNotice.ProcessingStatus.ANALYZED
            ).update(processing_status=ProcurementNotice.ProcessingStatus.ANALYSIS_QUEUED)
            AuditEvent.objects.create(
                actor=request.user.username,
                action="procurement.analysis_request.start",
                target_type="analysis_request",
                target_id=str(analysis_request.id),
                payload={
                    "batch_id": str(batch.id),
                    "candidate_count": len(candidate_ids),
                    "context_version": active.version,
                    "extraction_run": str(analysis_request.extraction_run_id or ""),
                    "acceptance_id": ACCEPTANCE_ID,
                    "locking_mode": "transaction-atomic-no-row-lock",
                },
            )
            work = [
                {
                    "notice_id": str(item.notice.id),
                    "notice_content_hash": item.content_hash,
                    "analysis_basis": notice_basis_payload(item.notice),
                }
                for item in work_items
            ]
        except Exception as exc:
            return _failed("create-batch", exc)

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
