from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_direct import (
    DirectOpportunity,
    OpportunityContact,
    OpportunityFollowUp,
    OpportunityResult,
)
from .permissions_extraction import IsManagerOrReadOnly
from .serializers_direct import (
    DirectOpportunityDetailSerializer,
    DirectOpportunityListSerializer,
    OpportunityContactSerializer,
    OpportunityFollowUpSerializer,
    OpportunityResultSerializer,
)


class DirectOpportunityViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    search_fields = ["title", "employer_name", "description", "domain", "province", "city", "next_action"]
    filterset_fields = ["opportunity_type", "stage", "responsible", "province", "probability", "confidentiality"]
    ordering_fields = ["next_action_due", "last_activity_at", "created_at", "updated_at", "probability_percent"]
    ordering = ["next_action_due", "-last_activity_at"]

    def get_queryset(self):
        return (
            DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)
            .select_related("responsible", "created_by", "primary_contact", "result", "result__contract")
            .prefetch_related("contacts", "follow_ups__created_by")
            .annotate(follow_up_count=Count("follow_ups"))
        )

    def get_serializer_class(self):
        if self.action in {"create", "retrieve", "update", "partial_update"}:
            return DirectOpportunityDetailSerializer
        return DirectOpportunityListSerializer

    def perform_create(self, serializer):
        values = {"created_by": self.request.user}
        if serializer.validated_data.get("responsible") is None:
            values["responsible"] = self.request.user
        if serializer.validated_data.get("next_action_due") is None:
            values["next_action_due"] = timezone.now() + timedelta(days=1)
        opportunity = serializer.save(**values)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.create",
            target_type="direct_opportunity",
            target_id=str(opportunity.id),
            payload={
                "title": opportunity.title,
                "employer_name": opportunity.employer_name,
                "stage": opportunity.stage,
                "next_action": opportunity.next_action,
            },
        )

    def perform_update(self, serializer):
        before_stage = serializer.instance.stage
        opportunity = serializer.save(last_activity_at=timezone.now())
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.update",
            target_type="direct_opportunity",
            target_id=str(opportunity.id),
            payload={"stage_before": before_stage, "stage_after": opportunity.stage},
        )


class OpportunityContactViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = OpportunityContact.objects.all()
    serializer_class = OpportunityContactSerializer
    search_fields = ["name", "position", "organization", "phone", "email"]
    ordering = ["organization", "name"]


class OpportunityFollowUpViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = OpportunityFollowUp.objects.select_related("opportunity", "created_by").all()
    serializer_class = OpportunityFollowUpSerializer
    filterset_fields = ["opportunity", "follow_up_type", "created_by"]
    ordering_fields = ["occurred_at", "created_at"]
    ordering = ["-occurred_at"]

    def perform_create(self, serializer):
        follow_up = serializer.save(created_by=self.request.user)
        opportunity = follow_up.opportunity
        opportunity.last_activity_at = follow_up.occurred_at
        if follow_up.next_action:
            opportunity.next_action = follow_up.next_action
        if follow_up.next_action_due:
            opportunity.next_action_due = follow_up.next_action_due
        if opportunity.stage in {DirectOpportunity.Stage.NEW, DirectOpportunity.Stage.REVIEWING}:
            opportunity.stage = DirectOpportunity.Stage.FOLLOWING_UP
        opportunity.save(
            update_fields=[
                "last_activity_at",
                "next_action",
                "next_action_due",
                "stage",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.follow_up",
            target_type="direct_opportunity",
            target_id=str(opportunity.id),
            payload={
                "follow_up_id": str(follow_up.id),
                "follow_up_type": follow_up.follow_up_type,
                "next_action": follow_up.next_action,
            },
        )


class OpportunityResultViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = OpportunityResult.objects.select_related("opportunity", "contract", "created_by").all()
    serializer_class = OpportunityResultSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["outcome", "result_date", "created_by"]
    ordering = ["-result_date"]

    def _apply_outcome(self, result):
        stage_by_outcome = {
            OpportunityResult.Outcome.WON: DirectOpportunity.Stage.WON,
            OpportunityResult.Outcome.LOST: DirectOpportunity.Stage.LOST,
            OpportunityResult.Outcome.STOPPED: DirectOpportunity.Stage.STOPPED,
            OpportunityResult.Outcome.DEFERRED: DirectOpportunity.Stage.DEFERRED,
            OpportunityResult.Outcome.CONVERTED_TO_TENDER: DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            OpportunityResult.Outcome.CONVERTED_TO_INQUIRY: DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            OpportunityResult.Outcome.CONVERTED_TO_CONTRACT: DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        }
        opportunity = result.opportunity
        opportunity.stage = stage_by_outcome[result.outcome]
        opportunity.last_activity_at = timezone.now()
        opportunity.save(update_fields=["stage", "last_activity_at", "updated_at"])

    def perform_create(self, serializer):
        result = serializer.save(created_by=self.request.user)
        self._apply_outcome(result)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.result.create",
            target_type="direct_opportunity",
            target_id=str(result.opportunity_id),
            payload={"result_id": str(result.id), "outcome": result.outcome},
        )

    def perform_update(self, serializer):
        result = serializer.save()
        self._apply_outcome(result)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.result.update",
            target_type="direct_opportunity",
            target_id=str(result.opportunity_id),
            payload={"result_id": str(result.id), "outcome": result.outcome},
        )
