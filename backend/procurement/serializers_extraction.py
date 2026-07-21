from rest_framework import serializers

from .models import ProcurementConnector
from .models_extraction import ExtractionError, ExtractionPage, ExtractionRun
from .serializers import ProcurementConnectorSerializer


class ExtractionPageSerializer(serializers.ModelSerializer):
    connector_key = serializers.CharField(source="connector.key", read_only=True)
    parse_status_label = serializers.CharField(source="get_parse_status_display", read_only=True)

    class Meta:
        model = ExtractionPage
        fields = [
            "id",
            "connector",
            "connector_key",
            "page_number",
            "url",
            "http_status",
            "content_hash",
            "response_bytes",
            "parse_status",
            "parse_status_label",
            "captured_at",
            "error_code",
            "error_message",
        ]
        read_only_fields = fields


class ExtractionErrorSerializer(serializers.ModelSerializer):
    connector_key = serializers.CharField(source="connector.key", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = ExtractionError
        fields = [
            "id",
            "connector",
            "connector_key",
            "page_number",
            "url",
            "category",
            "category_label",
            "safe_message",
            "retryable",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


class ExtractionRunSerializer(serializers.ModelSerializer):
    connector_ids = serializers.PrimaryKeyRelatedField(
        source="connectors",
        queryset=ProcurementConnector.objects.select_related("source").all(),
        many=True,
        write_only=True,
        required=True,
    )
    connectors = ProcurementConnectorSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)
    pages = ExtractionPageSerializer(many=True, read_only=True)
    errors = ExtractionErrorSerializer(many=True, read_only=True)

    class Meta:
        model = ExtractionRun
        fields = [
            "id",
            "trigger",
            "trigger_label",
            "status",
            "status_label",
            "connector_ids",
            "connectors",
            "requested_by",
            "requested_by_username",
            "date_from_raw",
            "date_to_raw",
            "include_details",
            "analyze_after_success",
            "page_cap",
            "started_at",
            "finished_at",
            "pages_processed",
            "records_seen",
            "records_new",
            "records_updated",
            "records_duplicate",
            "records_failed",
            "summary",
            "pages",
            "errors",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "trigger",
            "status",
            "requested_by",
            "started_at",
            "finished_at",
            "pages_processed",
            "records_seen",
            "records_new",
            "records_updated",
            "records_duplicate",
            "records_failed",
            "summary",
            "created_at",
            "updated_at",
        ]

    def validate_connector_ids(self, connectors):
        if not connectors:
            raise serializers.ValidationError("حداقل یک منبع فعال باید انتخاب شود.")
        unique_ids = {connector.id for connector in connectors}
        if len(unique_ids) != len(connectors):
            raise serializers.ValidationError("یک Connector چند بار انتخاب شده است.")
        unavailable = [
            connector.key
            for connector in connectors
            if not connector.enabled
            or not connector.source.enabled
            or connector.status == ProcurementConnector.Status.PENDING
        ]
        if unavailable:
            raise serializers.ValidationError(
                "Connectorهای غیرفعال یا در انتظار بررسی قابل اجرا نیستند: " + ", ".join(unavailable)
            )
        running_ids = set(
            ExtractionRun.objects.filter(
                status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING],
                connectors__in=connectors,
            ).values_list("connectors__id", flat=True)
        )
        conflicts = [connector.key for connector in connectors if connector.id in running_ids]
        if conflicts:
            raise serializers.ValidationError(
                "برای این Connectorها یک استخراج در صف یا در حال اجراست: " + ", ".join(conflicts)
            )
        return connectors

    def validate_page_cap(self, value):
        if value is not None and value > 500:
            raise serializers.ValidationError("حداکثر تعداد صفحات در اجرای دستی ۵۰۰ صفحه است.")
        return value

    def create(self, validated_data):
        connectors = validated_data.pop("connectors")
        run = ExtractionRun.objects.create(**validated_data)
        run.connectors.set(connectors)
        return run
