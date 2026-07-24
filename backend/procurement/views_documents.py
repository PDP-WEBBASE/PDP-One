from django.http import FileResponse
from django.utils.encoding import escape_uri_path
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_documents import ProcurementSubmissionDocument
from .serializers_documents import ProcurementSubmissionDocumentSerializer


class ProcurementSubmissionDocumentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = ProcurementSubmissionDocumentSerializer
    filterset_fields = ["case", "direct_opportunity", "document_type", "uploaded_by"]
    ordering_fields = ["created_at", "original_name", "document_type"]
    ordering = ["created_at"]

    def get_queryset(self):
        return ProcurementSubmissionDocument.objects.select_related(
            "case",
            "case__notice",
            "direct_opportunity",
            "uploaded_by",
        ).all()

    def perform_create(self, serializer):
        document = serializer.save(uploaded_by=self.request.user)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.submission_document.create",
            target_type="procurement_submission_document",
            target_id=str(document.id),
            payload={
                "case_id": str(document.case_id) if document.case_id else None,
                "direct_opportunity_id": (
                    str(document.direct_opportunity_id) if document.direct_opportunity_id else None
                ),
                "document_type": document.document_type,
                "original_name": document.original_name,
            },
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=document.original_name,
        )
        response["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{escape_uri_path(document.original_name)}"
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.submission_document.download",
            target_type="procurement_submission_document",
            target_id=str(document.id),
            payload={"original_name": document.original_name},
        )
        return response
