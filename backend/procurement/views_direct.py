from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
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
from .views import _filter_deadline_urgency


DIRECT_RECOMMENDED_STAGES = [
    DirectOpportunity.Stage.REVIEWING,
    DirectOpportunity.Stage.FOLLOWING_UP,
    DirectOpportunity.Stage.NEGOTIATING,
]
DIRECT_SELECTED_STAGES = [
    DirectOpportunity.Stage.SELECTED,
    DirectOpportunity.Stage.PREPARING,
]
DIRECT_RESULT_STAGES = [
    DirectOpportunity.Stage.WON,
    DirectOpportunity.Stage.LOST,
    DirectOpportunity.Stage.STOPPED,
    DirectOpportunity.Stage.DEFERRED,
    DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
    DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
]
DIRECT_ACTIVE_STAGES = [
    DirectOpportunity.Stage.SELECTED,
    DirectOpportunity.Stage.PREPARING,
    DirectOpportunity.Stage.SUBMITTED,
]


class DirectOpportunityViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    search_fields = [
        "reference_record__code", "title", "employer_name", "description",
        "domain", "province", "city", "next_action",
    ]
    filterset_fields = [
        "opportunity_type", "stage", "responsible", "province", "probability",
        "confidentiality",
    ]
    ordering_fields = [
        "next_action_due", "last_activity_at", "created_at", "updated_at",
        "probability_percent", "id",
    ]
    ordering = ["-last_activity_at", "-id"]

    def get_queryset(self):
        queryset = (
            DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)
            .select_related(
                "responsible", "created_by", "primary_contact", "result", "result__contract",
                "reference_record",
            )
            .prefetch_related("contacts", "follow_ups__created_by")
            .annotate(follow_up_count=Count("follow_ups"))
        )
        params = self.request.query_params
        workflow_view = params.get("workflow_view", "").strip()
        if workflow_view == "recommended":
            queryset = queryset.filter(stage__in=DIRECT_RECOMMENDED_STAGES)
        elif workflow_view == "selected":
            queryset = queryset.filter(stage__in=DIRECT_SELECTED_STAGES)
        elif workflow_view == "submitted":
            queryset = queryset.filter(stage=DirectOpportunity.Stage.SUBMITTED)
        elif workflow_view == "results":
            queryset = queryset.filter(stage__in=DIRECT_RESULT_STAGES)
        elif workflow_view == "active":
            queryset = queryset.filter(stage__in=DIRECT_ACTIVE_STAGES)

        importance = [value for raw in params.getlist("importance") for value in raw.split(",") if value]
        if importance:
            queryset = queryset.filter(importance__in=importance)

        urgencies = [value for raw in params.getlist("urgency") for value in raw.split(",") if value]
        if len(urgencies) == 1:
            queryset = _filter_deadline_urgency(queryset, "next_action_due", urgencies[0].strip())
        elif urgencies:
            urgency_query = Q()
            for urgency in urgencies:
                urgency_ids = _filter_deadline_urgency(queryset, "next_action_due", urgency.strip()).values("pk")
                urgency_query |= Q(pk__in=urgency_ids)
            queryset = queryset.filter(urgency_query)
        return queryset

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
                "reference_code": None,
                "title": opportunity.title,
                "employer_name": opportunity.employer_name,
                "stage": opportunity.stage,
                "next_action": opportunity.next_action,
            },
        )

    def perform_update(self, serializer):
        before_stage = serializer.instance.stage
        opportunity = serializer.save(last_activity_at=timezone.now())
        reference_code = None
        try:
            reference_code = opportunity.reference_record.code
        except AttributeError:
            pass
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.direct_opportunity.update",
            target_type="direct_opportunity",
            target_id=str(opportunity.id),
            payload={
                "stage_before": before_stage,
                "stage_after": opportunity.stage,
                "reference_code": reference_code,
            },
        )

    @action(detail=True, methods=["post"], url_path="soft-delete")
    def soft_delete(self, request, pk=None):
        opportunity = self.get_object()
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return Response(
                {"reason": ["برای حذف از فهرست، ثبت دلیل الزامی است."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        opportunity.soft_deleted_at = timezone.now()
        opportunity.last_activity_at = timezone.now()
        opportunity.save(update_fields=["soft_deleted_at", "last_activity_at", "updated_at"])
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.direct_opportunity.soft_delete",
            target_type="direct_opportunity",
            target_id=str(opportunity.id),
            payload={"reason": reason, "stage": opportunity.stage},
        )
        return Response({"deleted": True, "id": str(opportunity.id), "reason": reason})


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
            update_fields=["last_activity_at", "next_action", "next_action_due", "stage", "updated_at"]
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
