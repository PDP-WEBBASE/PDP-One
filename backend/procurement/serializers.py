from django.db import transaction
from rest_framework import serializers

from .models import (
    NoticeSourceLink,
    ProcurementCase,
    ProcurementConnector,
    ProcurementNotice,
    ProcurementSource,
    SourceNotice,
)


class ProcurementConnectorSerializer(serializers.ModelSerializer):
    notice_type_label = serializers.CharField(source="get_notice_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    operational_note = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementConnector
        fields = [
            "id", "source", "key", "notice_type", "notice_type_label", "enabled", "status",
            "status_label", "operational_note", "list_url_template", "parser_version", "supports_detail",
            "requires_browser", "page_size_hint", "max_pages", "timeout_seconds", "retry_count",
            "overlap_days", "last_success_at", "last_failure_at", "last_successful_page",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "source", "key", "notice_type", "list_url_template", "parser_version",
            "supports_detail", "requires_browser", "page_size_hint", "last_success_at",
            "last_failure_at", "last_successful_page", "created_at", "updated_at",
        ]

    def get_operational_note(self, obj):
        configuration = obj.source.configuration or {}
        controls = configuration.get("connector_controls") or {}
        note = controls.get(obj.key)
        return note if isinstance(note, dict) else None

    def validate_status(self, value):
        if value == ProcurementConnector.Status.PENDING:
            return value
        enabled = self.initial_data.get("enabled")
        if enabled is True and value == ProcurementConnector.Status.INACTIVE:
            raise serializers.ValidationError("Connector فعال نمی‌تواند وضعیت غیرفعال داشته باشد.")
        if enabled is False and value == ProcurementConnector.Status.ACTIVE:
            raise serializers.ValidationError("Connector غیرفعال نمی‌تواند وضعیت فعال داشته باشد.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        enabled = validated_data.get("enabled", instance.enabled)
        if "status" not in validated_data:
            if enabled and instance.status == ProcurementConnector.Status.INACTIVE:
                validated_data["status"] = ProcurementConnector.Status.ACTIVE
            elif not enabled:
                validated_data["status"] = ProcurementConnector.Status.INACTIVE
        connector = super().update(instance, validated_data)
        if connector.enabled and not connector.source.enabled:
            ProcurementSource.objects.filter(pk=connector.source_id).update(
                enabled=True,
                status=ProcurementSource.Status.ACTIVE,
            )
            connector.source.enabled = True
            connector.source.status = ProcurementSource.Status.ACTIVE
        return connector


class ProcurementSourceSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    connectors = ProcurementConnectorSerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementSource
        fields = [
            "id", "key", "name", "base_url", "enabled", "status", "status_label",
            "configuration", "last_success_at", "last_failure_at", "connectors",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "key", "name", "base_url", "configuration", "last_success_at",
            "last_failure_at", "created_at", "updated_at",
        ]

    @transaction.atomic
    def update(self, instance, validated_data):
        enabled = validated_data.get("enabled", instance.enabled)
        if "status" not in validated_data:
            if enabled and instance.status == ProcurementSource.Status.INACTIVE:
                validated_data["status"] = ProcurementSource.Status.ACTIVE
            elif not enabled:
                validated_data["status"] = ProcurementSource.Status.INACTIVE
        instance = super().update(instance, validated_data)
        connector_status = ProcurementConnector.Status.ACTIVE if enabled else ProcurementConnector.Status.INACTIVE
        instance.connectors.exclude(status=ProcurementConnector.Status.PENDING).update(
            enabled=enabled,
            status=connector_status,
        )
        return instance


class SourceNoticeSerializer(serializers.ModelSerializer):
    connector_key = serializers.CharField(source="connector.key", read_only=True)
    source_name = serializers.CharField(source="connector.source.name", read_only=True)
    detail_status_label = serializers.CharField(source="get_detail_status_display", read_only=True)

    class Meta:
        model = SourceNotice
        fields = [
            "id", "connector", "connector_key", "source_name", "source_record_id",
            "source_url", "detail_url", "source_declared_type", "title_raw", "employer_raw",
            "province_raw", "published_at_raw", "deadline_raw", "content_hash", "detail_status",
            "detail_status_label", "first_seen_at", "last_seen_at", "is_active",
        ]
        read_only_fields = fields


class NoticeSourceLinkSerializer(serializers.ModelSerializer):
    source_notice = SourceNoticeSerializer(read_only=True)
    match_type_label = serializers.CharField(source="get_match_type_display", read_only=True)

    class Meta:
        model = NoticeSourceLink
        fields = ["id", "source_notice", "match_type", "match_type_label", "confidence", "rationale", "created_at"]
        read_only_fields = fields


class ProcurementCaseSerializer(serializers.ModelSerializer):
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    responsible_username = serializers.CharField(source="responsible.username", read_only=True)
    submission_document_count = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementCase
        fields = [
            "id", "notice", "stage", "stage_label", "responsible", "responsible_username",
            "next_action", "next_action_due", "progress", "decision_reason",
            "protected_from_retention", "submission_document_count", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "protected_from_retention", "submission_document_count", "created_by",
            "created_at", "updated_at",
        ]

    def get_submission_document_count(self, obj):
        return obj.submission_documents.count()

    def validate(self, attrs):
        stage = attrs.get("stage", getattr(self.instance, "stage", ProcurementCase.Stage.SELECTED))
        reason = attrs.get("decision_reason", getattr(self.instance, "decision_reason", ""))
        if stage == ProcurementCase.Stage.DO_NOT_PARTICIPATE and not reason.strip():
            raise serializers.ValidationError(
                {"decision_reason": "برای تصمیم به عدم شرکت یا پاسخ، ثبت دلیل الزامی است."}
            )
        return attrs


class ProcurementNoticeListSerializer(serializers.ModelSerializer):
    reference_code = serializers.SerializerMethodField()
    notice_type_label = serializers.CharField(source="get_resolved_notice_type_display", read_only=True)
    type_resolution_status_label = serializers.CharField(source="get_type_resolution_status_display", read_only=True)
    processing_status_label = serializers.CharField(source="get_processing_status_display", read_only=True)
    case_stage = serializers.CharField(source="case.stage", read_only=True)
    case_stage_label = serializers.CharField(source="case.get_stage_display", read_only=True)
    source_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProcurementNotice
        fields = [
            "id", "reference_code", "resolved_notice_type", "notice_type_label", "type_resolution_status",
            "type_resolution_status_label", "title", "employer_name", "notice_number", "province",
            "published_date", "submission_deadline", "processing_status", "processing_status_label",
            "is_recommended", "case_stage", "case_stage_label", "source_count", "first_seen_at",
            "last_seen_at",
        ]
        read_only_fields = fields

    def get_reference_code(self, obj):
        try:
            return obj.reference_record.code
        except AttributeError:
            return None


class ProcurementNoticeDetailSerializer(ProcurementNoticeListSerializer):
    source_links = NoticeSourceLinkSerializer(many=True, read_only=True)
    case = ProcurementCaseSerializer(read_only=True)

    class Meta(ProcurementNoticeListSerializer.Meta):
        fields = ProcurementNoticeListSerializer.Meta.fields + [
            "normalized_title", "summary", "description", "conditions", "city",
            "execution_location", "date_metadata", "estimated_amount_rials",
            "guarantee_amount_rials", "qualification_text", "contact_text", "is_hidden",
            "retention_protected", "source_links", "case",
        ]
