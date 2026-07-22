from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models import ProcurementCase, ProcurementConnector, ProcurementNotice, ProcurementSource
from .models_direct import DirectOpportunity
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers import (
    ProcurementCaseSerializer,
    ProcurementConnectorSerializer,
    ProcurementNoticeDetailSerializer,
    ProcurementNoticeListSerializer,
    ProcurementSourceSerializer,
)


class ProcurementNoticeViewSet(viewsets.ReadOnlyModelViewSet):
    search_fields = [
        "reference_record__code",
        "title",
        "normalized_title",
        "summary",
        "description",
        "employer_name",
        "notice_number",
        "province",
        "city",
    ]
    filterset_fields = [
        "resolved_notice_type",
        "type_resolution_status",
        "processing_status",
        "is_recommended",
        "province",
        "employer_name",
    ]
    ordering_fields = [
        "published_date",
        "submission_deadline",
        "first_seen_at",
        "last_seen_at",
        "created_at",
    ]
    ordering = ["-last_seen_at"]

    def get_queryset(self):
        queryset = (
            ProcurementNotice.objects.filter(soft_deleted_at__isnull=True)
            .select_related("case", "case__responsible", "reference_record")
            .prefetch_related("source_links__source_notice__connector__source")
            .annotate(source_count=Count("source_links"))
        )
        notice_type = getattr(self, "fixed_notice_type", None)
        if notice_type:
            queryset = queryset.filter(resolved_notice_type=notice_type)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProcurementNoticeDetailSerializer
        return ProcurementNoticeListSerializer


class TenderViewSet(ProcurementNoticeViewSet):
    fixed_notice_type = ProcurementNotice.NoticeType.TENDER


class InquiryViewSet(ProcurementNoticeViewSet):
    fixed_notice_type = ProcurementNotice.NoticeType.INQUIRY


class ProcurementCaseViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = ProcurementCaseSerializer
    queryset = ProcurementCase.objects.select_related(
        "notice", "notice__reference_record", "responsible", "created_by"
    ).all()
    search_fields = [
        "notice__reference_record__code",
        "notice__title",
        "notice__employer_name",
        "next_action",
        "decision_reason",
    ]
    filterset_fields = ["stage", "responsible", "notice__resolved_notice_type"]
    ordering_fields = ["next_action_due", "created_at", "updated_at", "progress"]
    ordering = ["next_action_due", "-created_at"]

    def perform_create(self, serializer):
        case = serializer.save(created_by=self.request.user, protected_from_retention=True)
        ProcurementNotice.objects.filter(pk=case.notice_id).update(retention_protected=True)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.case.create",
            target_type="procurement_case",
            target_id=str(case.id),
            payload={"notice_id": str(case.notice_id), "stage": case.stage},
        )

    def perform_update(self, serializer):
        before_stage = serializer.instance.stage
        case = serializer.save()
        ProcurementNotice.objects.filter(pk=case.notice_id).update(retention_protected=True)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.case.update",
            target_type="procurement_case",
            target_id=str(case.id),
            payload={"stage_before": before_stage, "stage_after": case.stage},
        )


class ProcurementSourceViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = ProcurementSource.objects.prefetch_related("connectors").all()
    serializer_class = ProcurementSourceSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    filterset_fields = ["enabled", "status"]
    ordering = ["name"]

    def perform_update(self, serializer):
        before_enabled = serializer.instance.enabled
        source = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.source.update",
            target_type="procurement_source",
            target_id=str(source.id),
            payload={"enabled_before": before_enabled, "enabled_after": source.enabled},
        )


class ProcurementConnectorViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = ProcurementConnector.objects.select_related("source").all()
    serializer_class = ProcurementConnectorSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]
    filterset_fields = ["source", "enabled", "status", "notice_type"]
    ordering = ["source__name", "notice_type"]

    def perform_update(self, serializer):
        before_enabled = serializer.instance.enabled
        connector = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.connector.update",
            target_type="procurement_connector",
            target_id=str(connector.id),
            payload={"key": connector.key, "enabled_before": before_enabled, "enabled_after": connector.enabled},
        )


def _daily_notice_stats(notices, start_at, end_at):
    period = notices.filter(first_seen_at__gte=start_at, first_seen_at__lt=end_at)
    return {
        "total": period.count(),
        "tenders": period.filter(resolved_notice_type=ProcurementNotice.NoticeType.TENDER).count(),
        "inquiries": period.filter(resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY).count(),
        "recommended": period.filter(is_recommended=True).count(),
    }


@api_view(["GET"])
def procurement_dashboard(request):
    now = timezone.now()
    current_timezone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    today_start = timezone.make_aware(datetime.combine(today, time.min), current_timezone)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)

    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True)
    cases = ProcurementCase.objects.select_related("notice")
    active_cases = cases.exclude(
        stage__in=[
            ProcurementCase.Stage.WON,
            ProcurementCase.Stage.LOST,
            ProcurementCase.Stage.CANCELLED,
            ProcurementCase.Stage.RENEWED,
            ProcurementCase.Stage.DO_NOT_PARTICIPATE,
        ]
    )
    opportunities = DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)
    active_opportunities = opportunities.exclude(
        stage__in=[
            DirectOpportunity.Stage.WON,
            DirectOpportunity.Stage.LOST,
            DirectOpportunity.Stage.STOPPED,
            DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        ]
    )
    return Response(
        {
            "daily_notices": {
                "today": _daily_notice_stats(notices, today_start, tomorrow_start),
                "yesterday": _daily_notice_stats(notices, yesterday_start, today_start),
            },
            "notices": {
                "total": notices.count(),
                "tenders": notices.filter(resolved_notice_type=ProcurementNotice.NoticeType.TENDER).count(),
                "inquiries": notices.filter(resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY).count(),
                "recommended": notices.filter(is_recommended=True).count(),
                "type_review_required": notices.filter(
                    type_resolution_status=ProcurementNotice.TypeResolutionStatus.NEEDS_REVIEW
                ).count(),
                "deadline_passed": notices.filter(submission_deadline__lt=now).count(),
            },
            "cases": {
                "active": active_cases.count(),
                "overdue_next_actions": active_cases.filter(next_action_due__lt=now).count(),
                "without_responsible": active_cases.filter(responsible__isnull=True).count(),
                "by_stage": list(cases.values("stage").annotate(count=Count("id")).order_by("stage")),
            },
            "direct_opportunities": {
                "total": opportunities.count(),
                "active": active_opportunities.count(),
                "overdue_next_actions": active_opportunities.filter(next_action_due__lt=now).count(),
                "without_responsible": active_opportunities.filter(responsible__isnull=True).count(),
                "by_stage": list(opportunities.values("stage").annotate(count=Count("id")).order_by("stage")),
            },
            "sources": {
                "enabled_sites": ProcurementSource.objects.filter(enabled=True).count(),
                "enabled_connectors": ProcurementConnector.objects.filter(
                    enabled=True,
                    source__enabled=True,
                ).count(),
                "pending_connectors": ProcurementConnector.objects.filter(
                    Q(status=ProcurementConnector.Status.PENDING)
                    | Q(source__status=ProcurementSource.Status.PENDING)
                ).count(),
            },
        }
    )
