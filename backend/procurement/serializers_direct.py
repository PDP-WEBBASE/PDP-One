from rest_framework import serializers

from .models_direct import (
    DirectOpportunity,
    OpportunityContact,
    OpportunityFollowUp,
    OpportunityResult,
)
from .activity_domains import ACTIVITY_DOMAIN_LABELS, classify_activity_domain
from .opportunity_types import (
    AUTOMATED_DRAFT_SOURCE,
    HUMAN_SOURCE,
    UNCLASSIFIED,
    classify_business_opportunity_type,
)


class OpportunityContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityContact
        fields = [
            "id", "name", "position", "organization", "phone", "email", "how_met",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class OpportunityFollowUpSerializer(serializers.ModelSerializer):
    follow_up_type_label = serializers.CharField(source="get_follow_up_type_display", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = OpportunityFollowUp
        fields = [
            "id", "opportunity", "follow_up_type", "follow_up_type_label", "occurred_at",
            "summary", "next_action", "next_action_due", "created_by",
            "created_by_username", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class OpportunityResultSerializer(serializers.ModelSerializer):
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = OpportunityResult
        fields = [
            "id", "opportunity", "outcome", "outcome_label", "result_date", "reason",
            "notes", "contract", "created_by", "created_by_username", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        outcome = attrs.get("outcome", getattr(self.instance, "outcome", None))
        contract = attrs.get("contract", getattr(self.instance, "contract", None))
        if outcome == OpportunityResult.Outcome.CONVERTED_TO_CONTRACT and contract is None:
            raise serializers.ValidationError(
                {"contract": "برای تبدیل فرصت به قرارداد، انتخاب قرارداد الزامی است."}
            )
        if outcome != OpportunityResult.Outcome.CONVERTED_TO_CONTRACT and contract is not None:
            raise serializers.ValidationError(
                {"contract": "قرارداد فقط برای نتیجه «تبدیل به قرارداد» قابل ثبت است."}
            )
        return attrs


class DirectOpportunityListSerializer(serializers.ModelSerializer):
    reference_code = serializers.SerializerMethodField()
    opportunity_type_label = serializers.CharField(source="get_opportunity_type_display", read_only=True)
    business_opportunity_type_label = serializers.CharField(
        source="get_business_opportunity_type_display", read_only=True
    )
    business_opportunity_type_source_label = serializers.CharField(
        source="get_business_opportunity_type_source_display", read_only=True
    )
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    probability_label = serializers.CharField(source="get_probability_display", read_only=True)
    importance_label = serializers.CharField(source="get_importance_display", read_only=True)
    responsible_username = serializers.CharField(source="responsible.username", read_only=True)
    follow_up_count = serializers.IntegerField(read_only=True)
    activity_domain = serializers.SerializerMethodField()
    activity_domain_label = serializers.SerializerMethodField()

    class Meta:
        model = DirectOpportunity
        fields = [
            "id", "reference_code", "title", "employer_name", "opportunity_type",
            "opportunity_type_label", "business_opportunity_type",
            "business_opportunity_type_label", "business_opportunity_type_source",
            "business_opportunity_type_source_label", "business_opportunity_type_confidence",
            "business_opportunity_type_reason", "stage", "stage_label", "responsible",
            "responsible_username", "next_action", "next_action_due", "domain", "province",
            "probability", "probability_label", "probability_percent", "importance",
            "importance_label", "activity_domain", "activity_domain_label", "last_activity_at", "follow_up_count", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference_code", "business_opportunity_type_source",
            "business_opportunity_type_source_label", "business_opportunity_type_confidence",
            "business_opportunity_type_reason", "last_activity_at", "follow_up_count",
            "created_at", "updated_at",
        ]
        extra_kwargs = {
            "title": {"required": False, "allow_blank": True, "default": ""},
            "employer_name": {"required": False, "allow_blank": True, "default": ""},
            "next_action": {"required": False, "allow_blank": True, "default": ""},
        }

    def get_reference_code(self, obj):
        try:
            return obj.reference_record.code
        except AttributeError:
            return None

    def get_activity_domain(self, obj):
        return classify_activity_domain(obj.domain)

    def get_activity_domain_label(self, obj):
        return ACTIVITY_DOMAIN_LABELS[self.get_activity_domain(obj)]

    def validate_stage(self, value):
        terminal_stages = {
            DirectOpportunity.Stage.WON,
            DirectOpportunity.Stage.LOST,
            DirectOpportunity.Stage.STOPPED,
            DirectOpportunity.Stage.DEFERRED,
            DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        }
        if value in terminal_stages:
            raise serializers.ValidationError("نتیجه نهایی باید از بخش ثبت نتیجه وارد شود.")
        return value

    def _classify_business_type(self, validated_data):
        if "business_opportunity_type" in self.initial_data:
            validated_data["business_opportunity_type_source"] = HUMAN_SOURCE
            validated_data["business_opportunity_type_confidence"] = None
            validated_data["business_opportunity_type_reason"] = "نوع فرصت توسط کاربر تعیین شده است."
            return validated_data

        current = getattr(self.instance, "business_opportunity_type", UNCLASSIFIED)
        if current != UNCLASSIFIED:
            return validated_data
        classification = classify_business_opportunity_type(
            evidence_values=(
                validated_data.get("title", getattr(self.instance, "title", "")),
                validated_data.get("description", getattr(self.instance, "description", "")),
                validated_data.get("domain", getattr(self.instance, "domain", "")),
                validated_data.get("next_action", getattr(self.instance, "next_action", "")),
            )
        )
        if classification.value != UNCLASSIFIED:
            validated_data["business_opportunity_type"] = classification.value
            validated_data["business_opportunity_type_source"] = AUTOMATED_DRAFT_SOURCE
            validated_data["business_opportunity_type_confidence"] = classification.confidence
            validated_data["business_opportunity_type_reason"] = classification.reason
        return validated_data


class DirectOpportunityDetailSerializer(DirectOpportunityListSerializer):
    contact_ids = serializers.PrimaryKeyRelatedField(
        source="contacts", many=True, queryset=OpportunityContact.objects.all(),
        required=False, write_only=True,
    )
    contacts = OpportunityContactSerializer(many=True, read_only=True)
    primary_contact_detail = OpportunityContactSerializer(source="primary_contact", read_only=True)
    follow_ups = OpportunityFollowUpSerializer(many=True, read_only=True)
    result = OpportunityResultSerializer(read_only=True)

    class Meta(DirectOpportunityListSerializer.Meta):
        fields = DirectOpportunityListSerializer.Meta.fields + [
            "description", "city", "estimated_value_rials", "confidentiality", "source_text",
            "primary_contact", "primary_contact_detail", "contact_ids", "contacts", "follow_ups",
            "result", "created_by",
        ]
        read_only_fields = DirectOpportunityListSerializer.Meta.read_only_fields + ["created_by"]
        extra_kwargs = {
            **DirectOpportunityListSerializer.Meta.extra_kwargs,
            "description": {"required": False, "allow_blank": True},
            "city": {"required": False, "allow_blank": True},
            "domain": {"required": False, "allow_blank": True},
            "province": {"required": False, "allow_blank": True},
            "source_text": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            return attrs
        meaningful_fields = (
            "title", "employer_name", "description", "domain", "province", "city",
        )
        if not any(str(attrs.get(field, "")).strip() for field in meaningful_fields):
            raise serializers.ValidationError(
                {"detail": "برای ثبت اولیه، واردکردن حداقل یک اطلاعات معنادار الزامی است."}
            )
        return attrs

    def create(self, validated_data):
        validated_data = self._classify_business_type(validated_data)
        contacts = validated_data.pop("contacts", [])
        opportunity = DirectOpportunity.objects.create(**validated_data)
        if contacts:
            opportunity.contacts.set(contacts)
        return opportunity

    def update(self, instance, validated_data):
        validated_data = self._classify_business_type(validated_data)
        contacts = validated_data.pop("contacts", None)
        instance = super().update(instance, validated_data)
        if contacts is not None:
            instance.contacts.set(contacts)
        return instance
