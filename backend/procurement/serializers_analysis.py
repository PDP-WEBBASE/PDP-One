import hashlib
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .analysis_utils import get_active_context, notice_basis_hash
from .models import ProcurementNotice
from .models_analysis import (
    AnalysisBatch,
    AnalysisContextAttachment,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)
from .models_extraction import ExtractionRun
from .opportunity_types import (
    AI_DRAFT_SOURCE,
    HUMAN_SOURCE,
    UNASSIGNED_SOURCE,
    UNCLASSIFIED,
    classify_business_opportunity_type,
)


class AnalysisContextAttachmentSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)

    class Meta:
        model = AnalysisContextAttachment
        fields = [
            "id",
            "context_snapshot",
            "category",
            "category_label",
            "file",
            "original_name",
            "content_type",
            "size_bytes",
            "checksum_sha256",
            "uploaded_by",
            "uploaded_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "original_name",
            "content_type",
            "size_bytes",
            "checksum_sha256",
            "uploaded_by",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_context_snapshot(self, value):
        if value.status != AnalysisContextSnapshot.Status.DRAFT:
            raise serializers.ValidationError("فایل فقط به Snapshot پیش‌نویس قابل پیوست است.")
        return value

    def validate_file(self, value):
        allowed = {".txt", ".md", ".pdf", ".doc", ".docx"}
        suffix = Path(value.name).suffix.lower()
        if suffix not in allowed:
            raise serializers.ValidationError("فقط فایل‌های TXT، MD، PDF، DOC و DOCX مجاز هستند.")
        if value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError("حداکثر حجم هر فایل ۲۰ مگابایت است.")
        return value

    def create(self, validated_data):
        uploaded = validated_data["file"]
        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        return AnalysisContextAttachment.objects.create(
            original_name=Path(uploaded.name).name[:255],
            content_type=getattr(uploaded, "content_type", "")[:120],
            size_bytes=uploaded.size,
            checksum_sha256=digest.hexdigest(),
            uploaded_by=self.context["request"].user,
            **validated_data,
        )


class AnalysisContextSnapshotSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    activated_by_username = serializers.CharField(source="activated_by.username", read_only=True)
    attachments = AnalysisContextAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisContextSnapshot
        fields = [
            "id",
            "version",
            "status",
            "status_label",
            "role_text",
            "base_instructions",
            "analysis_prompt",
            "tender_prompt",
            "inquiry_prompt",
            "company_profile",
            "qualifications",
            "keywords",
            "experience_summary",
            "component_versions",
            "changed_components",
            "content_hash",
            "attachments",
            "activated_at",
            "activated_by",
            "activated_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "content_hash",
            "activated_at",
            "activated_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        status_value = attrs.get("status", getattr(self.instance, "status", AnalysisContextSnapshot.Status.DRAFT))
        if status_value == AnalysisContextSnapshot.Status.ACTIVE:
            raise serializers.ValidationError({"status": "فعال‌سازی فقط از مسیر اختصاصی و Audit‌شده انجام می‌شود."})
        prompt = attrs.get("analysis_prompt")
        if prompt is None:
            prompt = attrs.get("tender_prompt") or attrs.get("inquiry_prompt")
        if prompt is not None:
            attrs["analysis_prompt"] = prompt
            attrs["tender_prompt"] = prompt
            attrs["inquiry_prompt"] = prompt
        return attrs


class AnalysisRequestSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)
    context_version = serializers.IntegerField(source="context_snapshot.version", read_only=True)

    class Meta:
        model = AnalysisRequest
        fields = [
            "id",
            "trigger",
            "trigger_label",
            "command",
            "status",
            "status_label",
            "extraction_run",
            "context_snapshot",
            "context_version",
            "eligible_after",
            "requested_by",
            "requested_by_username",
            "started_at",
            "completed_at",
            "last_error",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "command",
            "status",
            "context_snapshot",
            "requested_by",
            "started_at",
            "completed_at",
            "last_error",
            "created_at",
            "updated_at",
        ]

    def validate_trigger(self, value):
        if value == AnalysisRequest.Trigger.SCHEDULED and not self.context.get("allow_scheduled", False):
            raise serializers.ValidationError("درخواست زمان‌بندی‌شده فقط از مسیر کنترل‌شده ChatGPT ایجاد می‌شود.")
        return value

    def validate_extraction_run(self, value):
        if value and value.status not in {
            ExtractionRun.Status.SUCCEEDED,
            ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
            ExtractionRun.Status.PARTIAL,
        }:
            raise serializers.ValidationError("تحلیل فقط پس از پایان یک استخراج موفق یا ناقص قابل شروع است.")
        return value

    def create(self, validated_data):
        active = get_active_context()
        if active is None:
            raise serializers.ValidationError({"context_snapshot": "هیچ Snapshot فعال تحلیل تعریف نشده است."})
        if not validated_data.get("extraction_run"):
            validated_data["extraction_run"] = (
                ExtractionRun.objects.filter(
                    status__in=[
                        ExtractionRun.Status.SUCCEEDED,
                        ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
                        ExtractionRun.Status.PARTIAL,
                    ]
                )
                .order_by("-finished_at", "-created_at")
                .first()
            )
        validated_data["context_snapshot"] = active
        validated_data["requested_by"] = self.context["request"].user
        validated_data["command"] = "PDP"
        return super().create(validated_data)


class AnalysisBatchSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    context_version = serializers.IntegerField(source="context_snapshot.version", read_only=True)

    class Meta:
        model = AnalysisBatch
        fields = [
            "id",
            "request",
            "context_snapshot",
            "context_version",
            "status",
            "status_label",
            "sequence",
            "item_count",
            "completed_count",
            "failed_count",
            "started_at",
            "finished_at",
            "summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "context_snapshot",
            "status",
            "sequence",
            "completed_count",
            "failed_count",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        request = validated_data["request"]
        if request.status not in {AnalysisRequest.Status.PENDING, AnalysisRequest.Status.PROCESSING}:
            raise serializers.ValidationError({"request": "این درخواست تحلیل قابل شروع نیست."})
        sequence = request.batches.count() + 1
        request.status = AnalysisRequest.Status.PROCESSING
        request.started_at = request.started_at or timezone.now()
        request.save(update_fields=["status", "started_at", "updated_at"])
        return AnalysisBatch.objects.create(
            context_snapshot=request.context_snapshot,
            sequence=sequence,
            status=AnalysisBatch.Status.PROCESSING,
            started_at=timezone.now(),
            **validated_data,
        )


class NoticeAnalysisDraftSerializer(serializers.ModelSerializer):
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    review_status_label = serializers.CharField(source="get_review_status_display", read_only=True)
    notice_title = serializers.CharField(source="notice.title", read_only=True)
    context_version = serializers.IntegerField(source="context_snapshot.version", read_only=True)
    business_opportunity_type_label = serializers.CharField(
        source="get_business_opportunity_type_display", read_only=True
    )

    class Meta:
        model = NoticeAnalysisDraft
        fields = [
            "id",
            "notice",
            "notice_title",
            "batch",
            "context_snapshot",
            "context_version",
            "notice_content_hash",
            "is_recommended",
            "score",
            "priority",
            "priority_label",
            "fit_for_pdp",
            "category",
            "business_opportunity_type",
            "business_opportunity_type_label",
            "business_opportunity_type_confidence",
            "business_opportunity_type_reason",
            "reason",
            "recommended_action",
            "matched_experience",
            "risk_notes",
            "confidence",
            "raw_output",
            "model_label",
            "review_status",
            "review_status_label",
            "analyzed_at",
            "created_by_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "context_snapshot",
            "notice_content_hash",
            "model_label",
            "review_status",
            "analyzed_at",
            "created_by_label",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        notice = attrs.get("notice")
        batch = attrs.get("batch")
        if batch and batch.status not in {AnalysisBatch.Status.OPEN, AnalysisBatch.Status.PROCESSING}:
            raise serializers.ValidationError({"batch": "این Batch برای ثبت تحلیل باز نیست."})
        if notice and notice.soft_deleted_at is not None:
            raise serializers.ValidationError({"notice": "فراخوان حذف‌شده قابل تحلیل نیست."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        notice = validated_data["notice"]
        batch = validated_data["batch"]
        classification = classify_business_opportunity_type(
            explicit=validated_data.get("business_opportunity_type"),
            explicit_confidence=validated_data.get("business_opportunity_type_confidence"),
            explicit_reason=validated_data.get("business_opportunity_type_reason"),
            evidence_values=(
                validated_data.get("category"),
                validated_data.get("fit_for_pdp"),
                validated_data.get("reason"),
                validated_data.get("recommended_action"),
                notice.title,
                notice.summary,
                notice.description,
                notice.conditions,
            ),
        )
        validated_data["business_opportunity_type"] = classification.value
        validated_data["business_opportunity_type_confidence"] = classification.confidence
        validated_data["business_opportunity_type_reason"] = classification.reason
        explicit_type_contract = "business_opportunity_type" in self.initial_data
        if explicit_type_contract and classification.value == UNCLASSIFIED and validated_data.get("is_recommended"):
            validated_data["is_recommended"] = False
            validated_data["score"] = min(int(validated_data.get("score", 0)), 59)
        basis_hash = notice_basis_hash(notice)
        existing = NoticeAnalysisDraft.objects.filter(
            notice=notice,
            notice_content_hash=basis_hash,
            context_snapshot=batch.context_snapshot,
        ).first()
        if existing:
            return existing
        draft = NoticeAnalysisDraft.objects.create(
            context_snapshot=batch.context_snapshot,
            notice_content_hash=basis_hash,
            model_label="ChatGPT Scheduled Task",
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
            created_by_label="ChatGPT",
            **validated_data,
        )
        notice.is_recommended = draft.is_recommended
        notice.processing_status = ProcurementNotice.ProcessingStatus.ANALYZED
        update_fields = ["is_recommended", "processing_status", "updated_at"]
        if notice.business_opportunity_type_source != HUMAN_SOURCE:
            notice.business_opportunity_type = classification.value
            notice.business_opportunity_type_source = (
                AI_DRAFT_SOURCE if classification.value != UNCLASSIFIED else UNASSIGNED_SOURCE
            )
            notice.business_opportunity_type_confidence = classification.confidence
            notice.business_opportunity_type_reason = classification.reason
            update_fields.extend([
                "business_opportunity_type", "business_opportunity_type_source",
                "business_opportunity_type_confidence", "business_opportunity_type_reason",
            ])
        notice.save(update_fields=update_fields)
        return draft
