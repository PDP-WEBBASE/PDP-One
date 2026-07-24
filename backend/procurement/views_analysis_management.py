from copy import deepcopy

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_analysis import AnalysisContextAttachment, AnalysisContextSnapshot
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers_analysis_management import (
    ManagedAnalysisContextAttachmentSerializer,
    ManagedAnalysisContextSnapshotSerializer,
)


_COMPONENT_FIELDS = {
    "role": ("role_text", "base_instructions"),
    "prompt": ("analysis_prompt", "tender_prompt", "inquiry_prompt"),
    "company_profile": ("company_profile",),
    "qualifications": ("qualifications",),
    "keywords": ("keywords",),
    "experience_summary": ("experience_summary",),
}


class ManagedAnalysisContextSnapshotViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = AnalysisContextSnapshot.objects.select_related("activated_by").prefetch_related("attachments").all()
    serializer_class = ManagedAnalysisContextSnapshotSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    filterset_fields = ["status", "version"]
    ordering_fields = ["version", "created_at", "activated_at"]
    ordering = ["-version"]

    def perform_create(self, serializer):
        snapshot = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.analysis_context.create",
            target_type="analysis_context_snapshot",
            target_id=str(snapshot.id),
            payload={"version": snapshot.version, "status": snapshot.status},
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.status != AnalysisContextSnapshot.Status.DRAFT:
            raise ValidationError("نسخه فعال یا بازنشسته قفل است؛ ابتدا نسخه ویرایشی جدید بسازید.")

        changed_components = []
        for component, fields in _COMPONENT_FIELDS.items():
            if any(
                field in serializer.validated_data
                and serializer.validated_data[field] != getattr(instance, field)
                for field in fields
            ):
                changed_components.append(component)

        component_versions = deepcopy(instance.component_versions or {})
        component_versions.setdefault("snapshot", instance.version)
        for component in changed_components:
            component_versions[component] = int(component_versions.get(component, 0)) + 1

        snapshot = serializer.save(
            component_versions=component_versions,
            changed_components=changed_components,
        )
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.analysis_context.update_draft",
            target_type="analysis_context_snapshot",
            target_id=str(snapshot.id),
            payload={
                "version": snapshot.version,
                "changed_components": changed_components,
                "content_hash": snapshot.content_hash,
            },
        )

    @action(detail=False, methods=["post"], url_path="create-draft")
    @transaction.atomic
    def create_draft(self, request):
        existing = (
            AnalysisContextSnapshot.objects.select_for_update()
            .filter(status=AnalysisContextSnapshot.Status.DRAFT)
            .order_by("-version")
            .first()
        )
        if existing is not None:
            data = self.get_serializer(existing).data
            data["reused_draft"] = True
            return Response(data, status=status.HTTP_200_OK)

        source_id = request.data.get("source_snapshot")
        source = None
        if source_id:
            source = AnalysisContextSnapshot.objects.select_for_update().filter(pk=source_id).first()
            if source is None:
                raise ValidationError({"source_snapshot": "نسخه مبنا پیدا نشد."})
        if source is None:
            source = (
                AnalysisContextSnapshot.objects.select_for_update()
                .filter(status=AnalysisContextSnapshot.Status.ACTIVE)
                .order_by("-version")
                .first()
            )
        if source is None:
            source = AnalysisContextSnapshot.objects.select_for_update().order_by("-version").first()

        latest = AnalysisContextSnapshot.objects.select_for_update().order_by("-version").first()
        next_version = (latest.version if latest else 0) + 1

        if source is not None:
            component_versions = deepcopy(source.component_versions or {})
            component_versions["snapshot"] = next_version
            draft = AnalysisContextSnapshot.objects.create(
                version=next_version,
                status=AnalysisContextSnapshot.Status.DRAFT,
                role_text=source.role_text,
                base_instructions=source.base_instructions,
                analysis_prompt=source.analysis_prompt,
                company_profile=deepcopy(source.company_profile),
                qualifications=deepcopy(source.qualifications),
                keywords=deepcopy(source.keywords),
                experience_summary=deepcopy(source.experience_summary),
                component_versions=component_versions,
                changed_components=[],
            )
            for attachment in source.attachments.all():
                AnalysisContextAttachment.objects.create(
                    context_snapshot=draft,
                    category=attachment.category,
                    file=attachment.file.name,
                    original_name=attachment.original_name,
                    content_type=attachment.content_type,
                    size_bytes=attachment.size_bytes,
                    checksum_sha256=attachment.checksum_sha256,
                    uploaded_by=attachment.uploaded_by,
                )
        else:
            component_versions = {"snapshot": next_version}
            draft = AnalysisContextSnapshot.objects.create(
                version=next_version,
                status=AnalysisContextSnapshot.Status.DRAFT,
                role_text=str(request.data.get("role_text", "")).strip(),
                base_instructions=str(request.data.get("base_instructions", "")).strip(),
                analysis_prompt=str(request.data.get("analysis_prompt", "")).strip(),
                company_profile=request.data.get("company_profile") or {},
                qualifications=request.data.get("qualifications") or [],
                keywords=request.data.get("keywords") or {"active": [], "excluded": []},
                experience_summary=request.data.get("experience_summary") or [],
                component_versions=component_versions,
                changed_components=["initial"],
            )

        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.analysis_context.create_draft",
            target_type="analysis_context_snapshot",
            target_id=str(draft.id),
            payload={
                "version": draft.version,
                "source_version": source.version if source else None,
                "attachments_copied": draft.attachments.count(),
            },
        )
        data = self.get_serializer(draft).data
        data["reused_draft"] = False
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        snapshot = self.get_object()
        if snapshot.status == AnalysisContextSnapshot.Status.ACTIVE:
            return Response(self.get_serializer(snapshot).data)
        if snapshot.status != AnalysisContextSnapshot.Status.DRAFT:
            raise ValidationError("فقط نسخه پیش‌نویس قابل فعال‌سازی است.")

        required = {
            "role_text": snapshot.role_text,
            "base_instructions": snapshot.base_instructions,
            "analysis_prompt": snapshot.analysis_prompt,
            "company_profile": snapshot.company_profile,
            "qualifications": snapshot.qualifications,
            "keywords": snapshot.keywords,
        }
        missing = [field for field, value in required.items() if not value]
        if missing:
            raise ValidationError({"detail": "برای فعال‌سازی، همه بخش‌های اصلی باید تکمیل شوند.", "missing": missing})

        AnalysisContextSnapshot.objects.select_for_update().filter(
            status=AnalysisContextSnapshot.Status.ACTIVE
        ).exclude(pk=snapshot.pk).update(status=AnalysisContextSnapshot.Status.RETIRED)
        snapshot.status = AnalysisContextSnapshot.Status.ACTIVE
        snapshot.activated_at = timezone.now()
        snapshot.activated_by = request.user
        snapshot.save()

        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.analysis_context.activate",
            target_type="analysis_context_snapshot",
            target_id=str(snapshot.id),
            payload={
                "version": snapshot.version,
                "content_hash": snapshot.content_hash,
                "changed_components": snapshot.changed_components,
            },
        )
        return Response(self.get_serializer(snapshot).data)


class ManagedAnalysisContextAttachmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = AnalysisContextAttachment.objects.select_related("context_snapshot", "uploaded_by").all()
    serializer_class = ManagedAnalysisContextAttachmentSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    filterset_fields = ["context_snapshot", "category"]
    ordering = ["category", "original_name"]

    def get_parsers(self):
        from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

        return [MultiPartParser(), FormParser(), JSONParser()]

    def perform_create(self, serializer):
        attachment = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.analysis_context.upload_file",
            target_type="analysis_context_attachment",
            target_id=str(attachment.id),
            payload={
                "context_snapshot": str(attachment.context_snapshot_id),
                "category": attachment.category,
                "original_name": attachment.original_name,
                "size_bytes": attachment.size_bytes,
                "checksum_sha256": attachment.checksum_sha256,
            },
        )

    def perform_destroy(self, instance):
        if instance.context_snapshot.status != AnalysisContextSnapshot.Status.DRAFT:
            raise ValidationError("فایل نسخه فعال یا بازنشسته قابل حذف نیست.")
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.analysis_context.delete_file",
            target_type="analysis_context_attachment",
            target_id=str(instance.id),
            payload={
                "context_snapshot": str(instance.context_snapshot_id),
                "category": instance.category,
                "original_name": instance.original_name,
                "checksum_sha256": instance.checksum_sha256,
            },
        )
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        attachment = self.get_object()
        response = FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=attachment.original_name,
            content_type=attachment.content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
