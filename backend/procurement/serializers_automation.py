from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .automation_utils import calculate_next_extraction
from .models_automation import ProcurementAutomationSettings


class ProcurementAutomationSettingsSerializer(serializers.ModelSerializer):
    cadence_label = serializers.CharField(source="get_cadence_display", read_only=True)
    updated_by_username = serializers.CharField(source="updated_by.username", read_only=True)

    class Meta:
        model = ProcurementAutomationSettings
        fields = [
            "id",
            "key",
            "enabled",
            "cadence",
            "cadence_label",
            "interval_minutes",
            "daily_time",
            "timezone_name",
            "analysis_delay_minutes",
            "scheduled_task_enabled",
            "manual_command",
            "next_extraction_at",
            "last_extraction_requested_at",
            "last_schedule_sync_at",
            "updated_by",
            "updated_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "key",
            "manual_command",
            "next_extraction_at",
            "last_extraction_requested_at",
            "last_schedule_sync_at",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def validate_interval_minutes(self, value):
        if value < 60:
            raise serializers.ValidationError("کمترین فاصله استخراج خودکار ۶۰ دقیقه است.")
        if value > 10080:
            raise serializers.ValidationError("فاصله استخراج نمی‌تواند بیشتر از یک هفته باشد.")
        return value

    def validate_analysis_delay_minutes(self, value):
        if value > 1440:
            raise serializers.ValidationError("تأخیر تحلیل نمی‌تواند بیشتر از ۲۴ ساعت باشد.")
        return value

    def validate_timezone_name(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("منطقه زمانی معتبر نیست.") from exc
        return value

    def validate(self, attrs):
        enabled = attrs.get("enabled", getattr(self.instance, "enabled", False))
        cadence = attrs.get("cadence", getattr(self.instance, "cadence", ProcurementAutomationSettings.Cadence.DAILY))
        daily_time = attrs.get("daily_time", getattr(self.instance, "daily_time", None))
        if enabled and cadence == ProcurementAutomationSettings.Cadence.DAILY and daily_time is None:
            raise serializers.ValidationError({"daily_time": "برای برنامه روزانه، ساعت استخراج الزامی است."})
        return attrs

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.updated_by = self.context["request"].user
        instance.manual_command = "PDP"
        instance.next_extraction_at = calculate_next_extraction(instance)
        instance.save(update_fields=["updated_by", "manual_command", "next_extraction_at", "updated_at"])
        return instance
