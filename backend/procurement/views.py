from datetime import date, datetime, time, timedelta

from django.db.models import Count, DateField, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models import ProcurementCase, ProcurementConnector, ProcurementNotice, ProcurementSource
from .models_direct import DirectOpportunity
from .models_extraction import ExtractionRun
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers import (
    ProcurementCaseSerializer,
    ProcurementConnectorSerializer,
    ProcurementNoticeDetailSerializer,
    ProcurementNoticeListSerializer,
    ProcurementSourceSerializer,
)


NOTICE_SELECTED_STAGES = [
    ProcurementCase.Stage.SELECTED,
    ProcurementCase.Stage.EVALUATING,
    ProcurementCase.Stage.PARTICIPATE,
    ProcurementCase.Stage.PREPARING,
    ProcurementCase.Stage.READY_TO_SUBMIT,
]
NOTICE_SUBMITTED_STAGES = [
    ProcurementCase.Stage.SUBMITTED,
    ProcurementCase.Stage.AWAITING_RESULT,
]
NOTICE_RESULT_STAGES = [
    ProcurementCase.Stage.WON,
    ProcurementCase.Stage.LOST,
    ProcurementCase.Stage.CANCELLED,
    ProcurementCase.Stage.RENEWED,
    ProcurementCase.Stage.DO_NOT_PARTICIPATE,
]


def _filter_deadline_urgency(queryset, field_name: str, urgency: str):
    now = timezone.now()
    in_24_hours = now + timedelta(hours=24)
    in_72_hours = now + timedelta(hours=72)
    in_168_hours = now + timedelta(hours=168)
    if urgency == "critical":
        return queryset.filter(**{f"{field_name}__lt": in_24_hours, f"{field_name}__isnull": False})
    if urgency == "high":
        return queryset.filter(**{f"{field_name}__gte": in_24_hours, f"{field_name}__lte": in_72_hours})
    if urgency == "medium":
        return queryset.filter(**{f"{field_name}__gt": in_72_hours, f"{field_name}__lte": in_168_hours})
    if urgency == "normal":
        return queryset.filter(**{f"{field_name}__gt": in_168_hours})
    if urgency == "unknown":
        return queryset.filter(**{f"{field_name}__isnull": True})
    return queryset


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
        "importance",
    ]
    ordering_fields = [
        "publication_sort",
        "published_date",
        "submission_deadline",
        "first_seen_at",
        "last_seen_at",
        "created_at",
        "id",
    ]
    ordering = ["-publication_sort", "-last_seen_at", "-id"]

    def get_queryset(self):
        queryset = (
            ProcurementNotice.objects.filter(soft_deleted_at__isnull=True)
            .select_related("case", "case__responsible", "reference_record")
            .prefetch_related("source_links__source_notice__connector__source")
            .annotate(
                source_count=Count("source_links", distinct=True),
                publication_sort=Coalesce(
                    "published_date",
                    Value(date(1900, 1, 1)),
                    output_field=DateField(),
                ),
            )
        )
        notice_type = getattr(self, "fixed_notice_type", None)
        if notice_type:
            queryset = queryset.filter(resolved_notice_type=notice_type)

        params = self.request.query_params
        recent_days = params.get("recent_days", "").strip()
        if recent_days:
            try:
                days = min(max(int(recent_days), 1), 365)
            except ValueError:
                days = 0
            if days:
                start_date = timezone.localdate() - timedelta(days=days - 1)
                queryset = queryset.filter(published_date__gte=start_date)

        workflow_view = params.get("workflow_view", "").strip()
        if workflow_view == "selected":
            queryset = queryset.filter(case__stage__in=NOTICE_SELECTED_STAGES)
        elif workflow_view == "submitted":
            queryset = queryset.filter(case__stage__in=NOTICE_SUBMITTED_STAGES)
        elif workflow_view == "results":
            queryset = queryset.filter(case__stage__in=NOTICE_RESULT_STAGES)
        elif workflow_view == "active":
            queryset = queryset.filter(case__stage__in=NOTICE_SELECTED_STAGES + NOTICE_SUBMITTED_STAGES)

        source_name = params.get("source_name", "").strip()
        if source_name:
            queryset = queryset.filter(
                source_links__source_notice__connector__source__name=source_name
            )

        queryset = _filter_deadline_urgency(
            queryset,
            "submission_deadline",
            params.get("urgency", "").strip(),
        )
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


def _connector_health_snapshot(connector: ProcurementConnector) -> dict:
    if not connector.enabled or not connector.source.enabled:
        return {
            "key": connector.key,
            "source": connector.source.name,
            "notice_type": connector.notice_type,
            "health": "disabled",
            "health_label": "غیرفعال",
            "requires_attention": False,
            "message": "این Connector توسط مدیر غیرفعال شده است.",
            "latest_run": None,
        }

    latest_run = (
        connector.extraction_runs.exclude(
            status__in=[ExtractionRun.Status.QUEUED, ExtractionRun.Status.RUNNING]
        )
        .order_by("-created_at")
        .first()
    )
    if latest_run is None:
        return {
            "key": connector.key,
            "source": connector.source.name,
            "notice_type": connector.notice_type,
            "health": "not_tested",
            "health_label": "آزمایش نشده",
            "requires_attention": True,
            "message": "هنوز اجرای تکمیل‌شده‌ای برای این Connector ثبت نشده است.",
            "latest_run": None,
        }

    connector_summary = (latest_run.summary.get("connectors") or {}).get(connector.key, {})
    completeness = connector_summary.get("completeness", "unknown")
    connector_status = connector_summary.get("status", latest_run.status)
    stop_reason = connector_summary.get("stop_reason", "")

    if connector_status == "failed" or latest_run.status == ExtractionRun.Status.FAILED:
        health = "failed"
        label = "ناموفق"
        message = "استخراج این منبع با خطا متوقف شده است."
        attention = True
    elif connector_status == "partial" or completeness == "incomplete":
        health = "incomplete"
        label = "استخراج ناقص"
        message = "پایان فهرست تأیید نشد؛ ممکن است بخشی از اطلاعات دریافت نشده باشد."
        attention = True
    elif completeness in {"limited_by_page_cap", "page_cap_reached_unverified"}:
        health = "limited"
        label = "محدود به سقف صفحات"
        message = "استخراج به سقف تعیین‌شده رسیده و کامل‌بودن کل فهرست تأیید نشده است."
        attention = True
    elif connector_status == "succeeded_with_warnings" or latest_run.status == ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS:
        health = "warning"
        label = "دارای هشدار"
        message = "استخراج انجام شده اما حداقل یک هشدار نیازمند بررسی وجود دارد."
        attention = True
    else:
        health = "healthy"
        label = "سالم"
        message = "آخرین استخراج بدون خطای کامل‌بودن انجام شده است."
        attention = False

    return {
        "key": connector.key,
        "source": connector.source.name,
        "notice_type": connector.notice_type,
        "health": health,
        "health_label": label,
        "requires_attention": attention,
        "message": message,
        "latest_run": {
            "id": str(latest_run.id),
            "status": latest_run.status,
            "created_at": latest_run.created_at,
            "finished_at": latest_run.finished_at,
            "requested_page_cap": connector_summary.get("requested_page_cap", latest_run.page_cap),
            "pages_processed": connector_summary.get("pages", 0),
            "last_successful_page": connector_summary.get("last_successful_page"),
            "reported_total_pages": connector_summary.get("reported_total_pages"),
            "records_seen": connector_summary.get("seen", 0),
            "warnings": connector_summary.get("warnings", 0),
            "completeness": completeness,
            "stop_reason": stop_reason,
            "suspicious_pages": connector_summary.get("suspicious_pages", []),
            "recovered_pages": connector_summary.get("recovered_pages", []),
        },
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
    connectors = list(
        ProcurementConnector.objects.select_related("source").order_by(
            "source__name", "notice_type"
        )
    )
    connector_health = [_connector_health_snapshot(connector) for connector in connectors]
    attention_connectors = sum(
        1 for item in connector_health if item["requires_attention"]
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
                "attention_connectors": attention_connectors,
                "all_healthy": attention_connectors == 0,
                "connector_health": connector_health,
            },
        }
    )
