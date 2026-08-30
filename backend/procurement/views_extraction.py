from django.db import transaction
from rest_framework import mixins
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_extraction import ExtractionRun
from .permissions_extraction import IsManagerOrReadOnly
from .serializers_extraction import ExtractionRunListSerializer, ExtractionRunSerializer
from .tasks import run_extraction


class ExtractionRunPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ExtractionRunViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = ExtractionRunSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = ExtractionRunPagination
    filterset_fields = ["status", "trigger", "requested_by"]
    ordering_fields = ["created_at", "started_at", "finished_at", "records_new", "records_failed"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return ExtractionRunListSerializer
        return ExtractionRunSerializer

    def get_queryset(self):
        queryset = ExtractionRun.objects.select_related("requested_by").prefetch_related(
            "connectors__source"
        )
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("pages__connector", "errors__connector")
        return queryset.all()

    def perform_create(self, serializer):
        run = serializer.save(requested_by=self.request.user)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.extraction.request",
            target_type="extraction_run",
            target_id=str(run.id),
            payload={
                "connector_keys": list(run.connectors.values_list("key", flat=True)),
                "include_details": run.include_details,
                "analyze_after_success": run.analyze_after_success,
                "page_cap": run.page_cap,
            },
        )
        transaction.on_commit(lambda: run_extraction.delay(str(run.id)))
