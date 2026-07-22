from rest_framework import serializers

from .models import ProcurementCase
from .models_direct import DirectOpportunity
from .models_documents import ProcurementSubmissionDocument


class ProcurementSubmissionDocumentSerializer(serializers.ModelSerializer):
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementSubmissionDocument
        fields = [
            "id",
            "case",
            "direct_opportunity",
            "document_type",
            "document_type_label",
            "file",
            "original_name",
            "description",
            "uploaded_by",
            "uploaded_by_username",
            "download_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "original_name",
            "uploaded_by",
            "uploaded_by_username",
            "download_url",
            "created_at",
            "updated_at",
        ]

    def get_download_url(self, obj):
        request = self.context.get("request")
        path = f"/api/v1/procurement/submission-documents/{obj.id}/download/"
        return request.build_absolute_uri(path) if request else path

    def validate(self, attrs):
        case = attrs.get("case")
        direct_opportunity = attrs.get("direct_opportunity")
        if bool(case) == bool(direct_opportunity):
            raise serializers.ValidationError(
                "هر سند باید دقیقاً به یک پرونده مناقصه/استعلام یا یک ارجاع مستقیم متصل باشد."
            )

        if case is not None:
            allowed_case_stages = {
                ProcurementCase.Stage.SELECTED,
                ProcurementCase.Stage.EVALUATING,
                ProcurementCase.Stage.PARTICIPATE,
                ProcurementCase.Stage.PREPARING,
                ProcurementCase.Stage.READY_TO_SUBMIT,
                ProcurementCase.Stage.SUBMITTED,
                ProcurementCase.Stage.AWAITING_RESULT,
                ProcurementCase.Stage.WON,
                ProcurementCase.Stage.LOST,
                ProcurementCase.Stage.CANCELLED,
            }
            if case.stage not in allowed_case_stages:
                raise serializers.ValidationError(
                    {"case": "بارگذاری سند فقط پس از ورود پرونده به مرحله منتخب مجاز است."}
                )

        if direct_opportunity is not None:
            allowed_direct_stages = {
                DirectOpportunity.Stage.SELECTED,
                DirectOpportunity.Stage.PREPARING,
                DirectOpportunity.Stage.SUBMITTED,
                DirectOpportunity.Stage.WON,
                DirectOpportunity.Stage.LOST,
                DirectOpportunity.Stage.STOPPED,
                DirectOpportunity.Stage.DEFERRED,
            }
            if direct_opportunity.stage not in allowed_direct_stages:
                raise serializers.ValidationError(
                    {"direct_opportunity": "بارگذاری سند فقط پس از ورود ارجاع مستقیم به مرحله منتخب مجاز است."}
                )
        return attrs

    def create(self, validated_data):
        uploaded_file = validated_data["file"]
        validated_data["original_name"] = uploaded_file.name[:255]
        return super().create(validated_data)
