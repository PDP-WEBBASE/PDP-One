from __future__ import annotations

import gzip
import hashlib
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .analysis_run_service import (
    active_run,
    cancel_run,
    claim_run_items,
    create_dataset,
    create_or_resume_run,
    import_result_records,
    pause_run,
    queue_summary,
    refresh_run_counters,
    resume_run,
    serialize_claimed_items,
)
from .models_analysis_runs import (
    ProcurementAnalysisDataset,
    ProcurementAnalysisImport,
    ProcurementAnalysisRun,
)
from .serializers_analysis_runs import (
    ProcurementAnalysisDatasetSerializer,
    ProcurementAnalysisImportSerializer,
    ProcurementAnalysisRunSerializer,
)
from .tasks_analysis_runs import export_analysis_dataset_task, initialize_analysis_run_task

logger = logging.getLogger(__name__)


def _allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


def _deny(request):
    if not _allowed(request.user):
        return Response({"detail": "این عملیات فقط برای مدیر سامانه یا سرویس رسمی ChatGPT مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    return None


def _actor(request) -> str:
    return getattr(request.user, "username", "") or "unknown"


def _start(request, run_type: str):
    denied = _deny(request)
    if denied:
        return denied
    trigger = str(request.data.get("trigger") or ProcurementAnalysisRun.Trigger.MANUAL_WEB)
    if trigger == ProcurementAnalysisRun.Trigger.SCHEDULED and getattr(request.user, "username", "") != "chatgpt-service":
        return Response({"detail": "Trigger زمان‌بندی‌شده فقط برای سرویس رسمی مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    scope = str(request.data.get("scope") or ProcurementAnalysisRun.Scope.ALL_PENDING)
    if scope not in ProcurementAnalysisRun.Scope.values:
        return Response({"detail": "Scope نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        run, created = create_or_resume_run(
            run_type=run_type,
            trigger=trigger,
            scope=scope,
            actor=_actor(request),
            requested_by=request.user,
            include_expired=bool(request.data.get("include_expired", False)),
            include_previously_analyzed=bool(request.data.get("include_previously_analyzed", False)),
            manual_notice_ids=list(request.data.get("manual_notice_ids") or []),
            shard_size=int(request.data.get("shard_size") or 250),
            deep_analysis_batch_size=int(request.data.get("deep_analysis_batch_size") or 25),
            parallel_workers=int(request.data.get("parallel_workers") or 4),
            max_retries_per_record=int(request.data.get("max_retries_per_record") or 2),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if created:
        initialize_analysis_run_task.delay(str(run.id))
    return Response(
        {
            "created": created,
            "continued_existing_run": not created,
            "run": ProcurementAnalysisRunSerializer(run).data,
            "draft_only": True,
            "requires_human_review": True,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_run_queue_summary(request):
    denied = _deny(request)
    if denied:
        return denied
    return Response(queue_summary())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_full_pending_analysis(request):
    return _start(request, ProcurementAnalysisRun.RunType.FULL_PENDING)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_incremental_analysis(request):
    return _start(request, ProcurementAnalysisRun.RunType.INCREMENTAL)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_analysis_run(request):
    denied = _deny(request)
    if denied:
        return denied
    run = active_run()
    if run is None:
        return Response({"run": None})
    refresh_run_counters(run)
    run.refresh_from_db()
    return Response({"run": ProcurementAnalysisRunSerializer(run).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_run_history(request):
    denied = _deny(request)
    if denied:
        return denied
    limit = max(1, min(int(request.query_params.get("limit", 25)), 100))
    runs = ProcurementAnalysisRun.objects.select_related("context_snapshot", "requested_by").order_by("-created_at")[:limit]
    return Response({"count": len(runs), "runs": ProcurementAnalysisRunSerializer(runs, many=True).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_run_status(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    run = get_object_or_404(ProcurementAnalysisRun.objects.select_related("context_snapshot", "requested_by"), pk=run_id)
    refresh_run_counters(run)
    run.refresh_from_db()
    return Response({"run": ProcurementAnalysisRunSerializer(run).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pause_analysis_run(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        run = pause_run(str(run_id), actor=_actor(request))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response({"run": ProcurementAnalysisRunSerializer(run).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_analysis_run(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        run = resume_run(str(run_id), actor=_actor(request))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response({"run": ProcurementAnalysisRunSerializer(run).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_analysis_run(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        run = cancel_run(str(run_id), actor=_actor(request))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response({"run": ProcurementAnalysisRunSerializer(run).data, "healthy_results_preserved": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_analysis_work(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        items = claim_run_items(
            str(run_id),
            worker_id=str(request.data.get("worker_id") or _actor(request)),
            limit=int(request.data.get("limit") or 25),
            lease_seconds=int(request.data.get("lease_seconds") or 900),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response({
        "run_id": str(run_id),
        "count": len(items),
        "items": serialize_claimed_items(items),
        "decision_is_draft": True,
        "requires_human_review": True,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def prepare_analysis_dataset(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    run = get_object_or_404(ProcurementAnalysisRun.objects.select_related("context_snapshot"), pk=run_id)
    try:
        dataset = create_dataset(
            run,
            scope=str(request.data.get("scope") or run.scope),
            shard_size=int(request.data.get("shard_size") or run.export_shard_size),
            compression=str(request.data.get("compression") or "gzip"),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    export_analysis_dataset_task.delay(str(dataset.id))
    AuditEvent.objects.create(
        actor=_actor(request),
        action="procurement.analysis_dataset.request",
        target_type="procurement_analysis_dataset",
        target_id=str(dataset.id),
        payload={"run_id": str(run.id), "scope": dataset.scope, "shard_size": dataset.shard_size},
    )
    return Response({"dataset": ProcurementAnalysisDatasetSerializer(dataset).data}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_dataset_status(request, dataset_id):
    denied = _deny(request)
    if denied:
        return denied
    dataset = get_object_or_404(ProcurementAnalysisDataset, pk=dataset_id)
    return Response({"dataset": ProcurementAnalysisDatasetSerializer(dataset).data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_analysis_dataset(request, dataset_id, filename):
    denied = _deny(request)
    if denied:
        return denied
    dataset = get_object_or_404(ProcurementAnalysisDataset, pk=dataset_id, status=ProcurementAnalysisDataset.Status.READY)
    allowed = {str(item.get("name")): str(item.get("path")) for item in dataset.files or []}
    path_value = allowed.get(filename)
    if not path_value:
        return Response({"detail": "فایل در Manifest این Dataset ثبت نشده است."}, status=status.HTTP_404_NOT_FOUND)
    path = Path(path_value).resolve()
    expected_root = (Path(settings.MEDIA_ROOT) / "procurement-analysis" / str(dataset.id)).resolve()
    if expected_root not in path.parents or not path.is_file():
        return Response({"detail": "مسیر فایل معتبر نیست."}, status=status.HTTP_404_NOT_FOUND)
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


def _uploaded_results(uploaded) -> tuple[list[dict], str]:
    digest = hashlib.sha256()
    temporary = Path(f"/tmp/pdp-analysis-results-{hashlib.sha256(uploaded.name.encode()).hexdigest()[:12]}")
    with temporary.open("wb") as handle:
        for chunk in uploaded.chunks():
            digest.update(chunk)
            handle.write(chunk)
    opener = gzip.open if uploaded.name.endswith(".gz") else open
    results: list[dict] = []
    try:
        with opener(temporary, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"خط {line_number} شیء JSON نیست.")
                results.append(value)
    finally:
        temporary.unlink(missing_ok=True)
    return results, digest.hexdigest()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def import_analysis_results(request, run_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        uploaded = request.FILES.get("result_file")
        if uploaded:
            results, calculated_hash = _uploaded_results(uploaded)
        else:
            results = list(request.data.get("results") or [])
            calculated_hash = hashlib.sha256(
                json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        supplied_hash = str(request.data.get("result_hash") or calculated_hash)
        if supplied_hash != calculated_hash:
            return Response({"detail": "Result Hash با محتوای ورودی تطابق ندارد."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            import_record = import_result_records(
                run_id=str(run_id),
                results=results,
                actor=_actor(request),
                dataset_id=str(request.data.get("dataset_id") or "") or None,
                result_hash=calculated_hash,
                dry_run=str(request.data.get("dry_run", "false")).lower() in {"1", "true", "yes"},
            )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:  # pragma: no cover - production diagnostic guard
        logger.exception("Procurement analysis result import failed for run %s", run_id)
        return Response(
            {
                "detail": "خطای داخلی ورود نتایج تحلیل ثبت شد؛ شناسه Run را برای بررسی نگه دارید.",
                "error_code": "procurement_import_internal_error",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"import": ProcurementAnalysisImportSerializer(import_record).data}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_import_status(request, import_id):
    denied = _deny(request)
    if denied:
        return denied
    record = get_object_or_404(ProcurementAnalysisImport, pk=import_id)
    return Response({"import": ProcurementAnalysisImportSerializer(record).data})
