from rest_framework import mixins
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_analysis import AnalysisContextAttachment
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers_analysis import AnalysisContextAttachmentSerializer


class AnalysisContextAttachmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = AnalysisContextAttachment.objects.select_related(
        "context_snapshot", "uploaded_by"
    ).all()
    serializer_class = AnalysisContextAttachmentSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["context_snapshot", "category"]
    ordering = ["category", "original_name"]

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
