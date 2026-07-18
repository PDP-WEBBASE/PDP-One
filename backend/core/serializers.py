from rest_framework import serializers
from .models import AnalysisReport, Contract, PaymentReceipt, Receivable

class ContractSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    class Meta:
        model = Contract
        fields = ["id", "code", "title", "employer", "field", "value_rials", "progress", "due_date", "status", "status_label", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]
    def validate_progress(self, value):
        if value > 100:
            raise serializers.ValidationError("Progress cannot exceed 100")
        return value

class AnalysisReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisReport
        fields = "__all__"
        read_only_fields = ["id", "requested_by", "review_status", "created_at", "updated_at"]


class ReceivableSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Receivable
        fields = [
            "id", "reference_code", "contract_code", "contract_title", "employer",
            "statement_title", "amount_rials", "received_rials", "due_date", "status",
            "status_label", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference_code", "status", "created_at", "updated_at"]

    def validate_amount_rials(self, value):
        if value <= 0:
            raise serializers.ValidationError("مبلغ مطالبه باید بیشتر از صفر باشد.")
        return value

    def validate(self, attrs):
        amount = attrs.get("amount_rials", getattr(self.instance, "amount_rials", 0))
        received = attrs.get("received_rials", getattr(self.instance, "received_rials", 0))
        if received < 0:
            raise serializers.ValidationError({"received_rials": "مبلغ وصول‌شده نمی‌تواند منفی باشد."})
        if amount and received > amount:
            raise serializers.ValidationError({"received_rials": "مبلغ وصول‌شده نمی‌تواند بیشتر از مبلغ مطالبه باشد."})
        return attrs


class PaymentReceiptSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    receivable_reference = serializers.CharField(source="receivable.reference_code", read_only=True)

    class Meta:
        model = PaymentReceipt
        fields = [
            "id", "receivable", "receivable_reference", "amount_rials", "received_date",
            "tracking_code", "note", "status", "status_label", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def validate_amount_rials(self, value):
        if value <= 0:
            raise serializers.ValidationError("مبلغ دریافت باید بیشتر از صفر باشد.")
        return value
