from rest_framework import serializers

from .models_analysis_runs import (
    ProcurementAnalysisDataset,
    ProcurementAnalysisImport,
    ProcurementAnalysisRun,
    ProcurementAnalysisRunItem,
)


class ProcurementAnalysisRunSerializer(serializers.ModelSerializer):
    run_type_label = serializers.CharField(source="get_run_type_display", read_only=True)
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    scope_label = serializers.CharField(source="get_scope_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    context_version = serializers.IntegerField(source="context_snapshot.version", read_only=True)
    context_hash = serializers.CharField(source="context_snapshot.content_hash", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)

    class Meta:
        model = ProcurementAnalysisRun
        fields = [
            "id",
            "run_type",
            "run_type_label",
            "trigger",
            "trigger_label",
            "scope",
            "scope_label",
            "status",
            "status_label",
            "context_snapshot",
            "context_version",
            "context_hash",
            "extraction_run",
            "analysis_request",
            "requested_by",
            "requested_by_username",
            "include_expired",
            "include_previously_analyzed",
            "manual_notice_ids",
            "export_shard_size",
            "deep_analysis_batch_size",
            "parallel_workers",
            "max_retries_per_record",
            "checkpoint_after_each_shard",
            "started_at",
            "finished_at",
            "heartbeat_at",
            "last_checkpoint",
            "counters",
            "metadata",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProcurementAnalysisRunItemSerializer(serializers.ModelSerializer):
    notice_title = serializers.CharField(source="notice.title", read_only=True)
    notice_type = serializers.CharField(source="notice.resolved_notice_type", read_only=True)
    employer = serializers.CharField(source="notice.employer_name", read_only=True)

    class Meta:
        model = ProcurementAnalysisRunItem
        fields = [
            "id",
            "run",
            "notice",
            "notice_title",
            "notice_type",
            "employer",
            "notice_content_hash",
            "context_hash",
            "status",
            "analysis_reason",
            "deadline_priority",
            "shard_number",
            "sequence",
            "claimed_by",
            "claimed_at",
            "claim_expires_at",
            "attempts",
            "last_error",
            "screening",
            "result_metadata",
            "draft",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProcurementAnalysisDatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementAnalysisDataset
        fields = [
            "id",
            "run",
            "context_snapshot",
            "status",
            "scope",
            "schema_version",
            "application_commit",
            "migration_head",
            "compression",
            "shard_size",
            "record_count",
            "shard_count",
            "files",
            "counts",
            "hashes",
            "checkpoint",
            "validation",
            "started_at",
            "finished_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProcurementAnalysisImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementAnalysisImport
        fields = [
            "id",
            "run",
            "dataset",
            "status",
            "result_hash",
            "dry_run",
            "checkpoint",
            "counts",
            "report",
            "started_at",
            "finished_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
