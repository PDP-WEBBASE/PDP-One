from rest_framework import serializers

from .models_direct import (
    DirectOpportunity,
    OpportunityContact,
    OpportunityFollowUp,
    OpportunityResult,
)


class OpportunityContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityContact
        fields = [
            "id",
            "name",
            "position",
            "organization",
            "phone",
            "email",
            "how_met",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class OpportunityFollowUpSerializer(serializers.ModelSerializer):
    follow_up_type_label = serializers.CharField(source="get_follow_up_type_display", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = OpportunityFollowUp
        fields = [
            "id",
            "opportunity",
            "follow_up_type",
            "follow_up_type_label",
            "occurred_at",
            "summary",
            "next_action",
            "next_action_due",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class OpportunityResultSerializer(serializers.ModelSerializer):
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = OpportunityResult
        fields = [
            "id",
            "opportunity",
            "outcome",
            "outcome_label",
            "result_date",
            "reason",
            "notes",
            "contract",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
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
    opportunity_type_label = serializers.CharField(source="get_opportunity_type_display", read_only=True)
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    probability_label = serializers.CharField(source="get_probability_display", read_only=True)
    responsible_username = serializers.CharField(source="responsible.username", read_only=True)
    follow_up_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DirectOpportunity
        fields = [
            "id",
            "title",
            "employer_name",
            "opportunity_type",
            "opportunity_type_label",
            "stage",
            "stage_label",
            "responsible",
            "responsible_username",
            "next_action",
            "next_action_due",
            "domain",
            "province",
            "probability",
            "probability_label",
            "probability_percent",
            "last_activity_at",
            "follow_up_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_activity_at",
            "follow_up_count",
            "created_at",
            "updated_at",
        ]

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


class DirectOpportunityDetailSerializer(DirectOpportunityListSerializer):
    contact_ids = serializers.PrimaryKeyRelatedField(
        source="contacts",
        many=True,
        queryset=OpportunityContact.objects.all(),
        required=False,
        write_only=True,
    )
    contacts = OpportunityContactSerializer(many=True, read_only=True)
    primary_contact_detail = OpportunityContactSerializer(source="primary_contact", read_only=True)
    follow_ups = OpportunityFollowUpSerializer(many=True, read_only=True)
    result = OpportunityResultSerializer(read_only=True)

    class Meta(DirectOpportunityListSerializer.Meta):
        fields = DirectOpportunityListSerializer.Meta.fields + [
            "description",
            "city",
            "estimated_value_rials",
            "confidentiality",
            "source_text",
            "primary_contact",
            "primary_contact_detail",
            "contact_ids",
            "contacts",
            "follow_ups",
            "result",
            "created_by",
        ]
        read_only_fields = DirectOpportunityListSerializer.Meta.read_only_fields + ["created_by"]

    def create(self, validated_data):
        contacts = validated_data.pop("contacts", [])
        opportunity = DirectOpportunity.objects.create(**validated_data)
        if contacts:
            opportunity.contacts.set(contacts)
        return opportunity

    def update(self, instance, validated_data):
        contacts = validated_data.pop("contacts", None)
        instance = super().update(instance, validated_data)
        if contacts is not None:
            instance.contacts.set(contacts)
        return instance
