from pathlib import Path

from rest_framework import serializers

from .models_analysis import AnalysisContextAttachment, AnalysisContextSnapshot
from .serializers_analysis import (
    AnalysisContextAttachmentSerializer,
    AnalysisContextSnapshotSerializer,
)


class ManagedAnalysisContextSnapshotSerializer(AnalysisContextSnapshotSerializer):
    is_locked = serializers.SerializerMethodField()

    class Meta(AnalysisContextSnapshotSerializer.Meta):
        fields = [*AnalysisContextSnapshotSerializer.Meta.fields, "is_locked"]
        read_only_fields = [*AnalysisContextSnapshotSerializer.Meta.read_only_fields, "is_locked"]

    def get_is_locked(self, obj):
        return obj.status != AnalysisContextSnapshot.Status.DRAFT

    def validate_company_profile(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("پروفایل شرکت باید یک شیء JSON باشد.")
        return value

    def validate_qualifications(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("صلاحیت‌ها باید به‌صورت فهرست ذخیره شوند.")
        return value

    def validate_keywords(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("کلیدواژه‌ها باید یک شیء JSON باشند.")
        for key in ("active", "excluded"):
            if key in value and not isinstance(value[key], list):
                raise serializers.ValidationError({key: "مقدار باید فهرست باشد."})
        return value

    def validate_experience_summary(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("سوابق و تجربیات باید به‌صورت فهرست ذخیره شوند.")
        return value

    def update(self, instance, validated_data):
        if instance.status != AnalysisContextSnapshot.Status.DRAFT:
            raise serializers.ValidationError("نسخه فعال یا بازنشسته قفل است؛ ابتدا نسخه ویرایشی جدید بسازید.")
        return super().update(instance, validated_data)


class ManagedAnalysisContextAttachmentSerializer(AnalysisContextAttachmentSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta(AnalysisContextAttachmentSerializer.Meta):
        fields = [*AnalysisContextAttachmentSerializer.Meta.fields, "download_url"]
        read_only_fields = [*AnalysisContextAttachmentSerializer.Meta.read_only_fields, "download_url"]

    def get_download_url(self, obj):
        request = self.context.get("request")
        path = f"/api/v1/procurement/analysis-context-files/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def validate_file(self, value):
        allowed = {".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx"}
        suffix = Path(value.name).suffix.lower()
        if suffix not in allowed:
            raise serializers.ValidationError("فرمت فایل مجاز نیست.")
        if value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError("حداکثر حجم هر فایل ۲۰ مگابایت است.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        uploaded = attrs.get("file")
        category = attrs.get("category")
        if not uploaded or not category:
            return attrs
        suffix = Path(uploaded.name).suffix.lower()
        category_extensions = {
            AnalysisContextAttachment.Category.PROMPT_REFERENCE: {".txt", ".md", ".pdf", ".doc", ".docx"},
            AnalysisContextAttachment.Category.KEYWORDS: {".txt", ".md", ".csv", ".xls", ".xlsx"},
            AnalysisContextAttachment.Category.COMPANY_PROFILE: {".txt", ".md", ".pdf", ".doc", ".docx"},
            AnalysisContextAttachment.Category.QUALIFICATIONS: {".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx"},
            AnalysisContextAttachment.Category.RESUME: {".txt", ".md", ".pdf", ".doc", ".docx"},
            AnalysisContextAttachment.Category.OTHER: {".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx"},
        }
        if suffix not in category_extensions[category]:
            raise serializers.ValidationError({"file": "فرمت فایل با دسته انتخاب‌شده سازگار نیست."})
        return attrs
