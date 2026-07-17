from rest_framework import serializers
from .models import AnalysisReport, Contract

class ContractSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    class Meta:
        model = Contract
        fields = ["id", "code", "title", "employer", "field", "value_rials", "progress", "due_date", "status", "status_label", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    def validate_progress(self, value):
        if value > 100:
            raise serializers.ValidationError("Progress cannot exceed 100")
        return value

class AnalysisReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisReport
        fields = "__all__"
        read_only_fields = ["id", "requested_by", "created_at", "updated_at"]

