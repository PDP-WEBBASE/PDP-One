from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .analysis_utils import get_active_context, notice_basis_hash, notice_basis_payload
from .models import ProcurementNotice
from .models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)
from .models_extraction import ExtractionRun
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers import ProcurementNoticeDetailSerializer
from .serializers_analysis import (
    AnalysisBatchSerializer,
    AnalysisContextSnapshotSerializer,
    AnalysisRequestSerializer,
    NoticeAnalysisDraftSerializer,
)


class AnalysisContextSnapshotViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = AnalysisContextSnapshot.objects.select_related("activated_by").all()
    serializer_class = AnalysisContextSnapshotSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    filterset_fields = ["status", "version"]
    ordering = ["-version"]

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        snapshot = self.get_object()
        AnalysisContextSnapshot.objects.filter(status=AnalysisContextSnapshot.Status.ACTIVE).exclude(pk=snapshot.pk).update(
            status=AnalysisContextSnapshot.Status.RETIRED
        )
        snapshot.status = AnalysisContextSnapshot.Status.ACTIVE
        snapshot.activated_at = timezone.now()
        snapshot.activated_by = request.user
        snapshot.save()
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.analysis_context.activate",
            target_type="analysis_context_snapshot",
            target_id=str(snapshot.id),
            payload={"version": snapshot.version, "content_hash": snapshot.content_hash},
        )
        return Response(self.get_serializer(snapshot).data)


class AnalysisRequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = AnalysisRequest.objects.select_related(
        "extraction_run", "context_snapshot", "requested_by"
    ).all()
    serializer_class = AnalysisRequestSerializer
    filterset_fields = ["status", "trigger", "extraction_run", "context_snapshot"]
    ordering_fields = ["created_at", "eligible_after", "completed_at"]
    ordering = ["-created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["allow_scheduled"] = getattr(self.request.user, "username", "") == "chatgpt-service"
        return context

    def perform_create(self, serializer):
        analysis_request = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.analysis_request.create",
            target_type="analysis_request",
            target_id=str(analysis_request.id),
            payload={
                "trigger": analysis_request.trigger,
                "command": "PDP",
                "context_version": analysis_request.context_snapshot.version,
                "extraction_run": str(analysis_request.extraction_run_id or ""),
            },
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        analysis_request = self.get_object()
        requested_status = request.data.get("status", AnalysisRequest.Status.COMPLETED)
        if requested_status not in {
            AnalysisRequest.Status.COMPLETED,
            AnalysisRequest.Status.NO_CHANGES,
            AnalysisRequest.Status.FAILED,
        }:
            return Response({"detail": "وضعیت پایان نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
        analysis_request.status = requested_status
        analysis_request.completed_at = timezone.now()
        analysis_request.last_error = str(request.data.get("last_error", ""))[:1000]
        analysis_request.metadata = {**analysis_request.metadata, **request.data.get("metadata", {})}
        analysis_request.save(update_fields=["status", "completed_at", "last_error", "metadata", "updated_at"])
        return Response(self.get_serializer(analysis_request).data)


class AnalysisBatchViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = AnalysisBatch.objects.select_related("request", "context_snapshot").all()
    serializer_class = AnalysisBatchSerializer
    filterset_fields = ["status", "request", "context_snapshot"]
    ordering = ["request", "sequence"]

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def complete(self, request, pk=None):
        batch = self.get_object()
        failed_count = max(0, int(request.data.get("failed_count", batch.failed_count)))
        completed_count = max(0, int(request.data.get("completed_count", batch.completed_count)))
        if failed_count and completed_count:
            final_status = AnalysisBatch.Status.PARTIAL
        elif failed_count:
            final_status = AnalysisBatch.Status.FAILED
        else:
            final_status = AnalysisBatch.Status.COMPLETED
        batch.failed_count = failed_count
        batch.completed_count = completed_count
        batch.status = final_status
        batch.finished_at = timezone.now()
        batch.summary = request.data.get("summary", {})
        batch.save(update_fields=["failed_count", "completed_count", "status", "finished_at", "summary", "updated_at"])
        return Response(self.get_serializer(batch).data)


class NoticeAnalysisDraftViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = NoticeAnalysisDraft.objects.select_related(
        "notice", "batch", "context_snapshot"
    ).all()
    serializer_class = NoticeAnalysisDraftSerializer
    filterset_fields = [
        "notice",
        "batch",
        "context_snapshot",
        "is_recommended",
        "priority",
        "review_status",
    ]
    ordering_fields = ["analyzed_at", "score", "confidence", "created_at"]
    ordering = ["-analyzed_at"]

    def perform_create(self, serializer):
        draft = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.notice_analysis.create_draft",
            target_type="notice_analysis_draft",
            target_id=str(draft.id),
            payload={
                "notice_id": str(draft.notice_id),
                "batch_id": str(draft.batch_id),
                "context_version": draft.context_snapshot.version,
                "recommended": draft.is_recommended,
            },
        )


@api_view(["GET"])
def analysis_context_manifest(request):
    active = get_active_context()
    if active is None:
        return Response(
            {"configured": False, "detail": "هیچ Snapshot فعال تحلیل تعریف نشده است."},
            status=status.HTTP_409_CONFLICT,
        )
    known_version = request.query_params.get("known_version")
    try:
        known_version_number = int(known_version) if known_version is not None else None
    except ValueError:
        return Response({"detail": "known_version باید عدد باشد."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "configured": True,
            "context_version": active.version,
            "content_hash": active.content_hash,
            "component_versions": active.component_versions,
            "changed": known_version_number is None or known_version_number != active.version,
            "changed_components": active.changed_components if known_version_number != active.version else [],
            "snapshot_id": str(active.id),
        }
    )


@api_view(["GET"])
def active_analysis_context(request):
    active = get_active_context()
    if active is None:
        return Response(
            {"configured": False, "detail": "هیچ Snapshot فعال تحلیل تعریف نشده است."},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(AnalysisContextSnapshotSerializer(active).data)


@api_view(["GET"])
def latest_extraction_run(request):
    run = (
        ExtractionRun.objects.filter(
            status__in=[
                ExtractionRun.Status.SUCCEEDED,
                ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
                ExtractionRun.Status.PARTIAL,
            ]
        )
        .prefetch_related("connectors")
        .order_by("-finished_at", "-created_at")
        .first()
    )
    if run is None:
        return Response({"available": False, "detail": "استخراج تکمیل‌شده‌ای وجود ندارد."})
    return Response(
        {
            "available": True,
            "id": str(run.id),
            "status": run.status,
            "finished_at": run.finished_at,
            "records_new": run.records_new,
            "records_updated": run.records_updated,
            "records_failed": run.records_failed,
            "connector_keys": list(run.connectors.values_list("key", flat=True)),
        }
    )


@api_view(["GET"])
def analysis_queue(request):
    active = get_active_context()
    if active is None:
        return Response(
            {"configured": False, "detail": "هیچ Snapshot فعال تحلیل تعریف نشده است."},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        limit = min(max(int(request.query_params.get("limit", 20)), 1), 50)
    except ValueError:
        return Response({"detail": "limit باید عدد باشد."}, status=status.HTTP_400_BAD_REQUEST)

    candidates = (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        .exclude(processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED)
        .prefetch_related("source_links__source_notice")
        .order_by("-last_seen_at")[:250]
    )
    items = []
    for notice in candidates:
        basis_hash = notice_basis_hash(notice)
        already_done = NoticeAnalysisDraft.objects.filter(
            notice=notice,
            context_snapshot=active,
            notice_content_hash=basis_hash,
        ).exists()
        if already_done:
            continue
        items.append(
            {
                "id": str(notice.id),
                "type": notice.resolved_notice_type,
                "title": notice.title,
                "employer_name": notice.employer_name,
                "province": notice.province,
                "published_date": notice.published_date,
                "submission_deadline": notice.submission_deadline,
                "processing_status": notice.processing_status,
                "notice_content_hash": basis_hash,
            }
        )
        if len(items) >= limit:
            break
    return Response({"context_version": active.version, "count": len(items), "items": items})


@api_view(["GET"])
def notice_analysis_context(request, notice_id):
    try:
        notice = (
            ProcurementNotice.objects.prefetch_related("source_links__source_notice__connector__source")
            .get(pk=notice_id, soft_deleted_at__isnull=True)
        )
    except ProcurementNotice.DoesNotExist:
        return Response({"detail": "فراخوان پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)
    active = get_active_context()
    latest_draft = notice.analysis_drafts.select_related("context_snapshot").order_by("-analyzed_at").first()
    return Response(
        {
            "notice": ProcurementNoticeDetailSerializer(notice).data,
            "analysis_basis": notice_basis_payload(notice),
            "notice_content_hash": notice_basis_hash(notice),
            "active_context_version": active.version if active else None,
            "latest_analysis": NoticeAnalysisDraftSerializer(latest_draft).data if latest_draft else None,
        }
    )
