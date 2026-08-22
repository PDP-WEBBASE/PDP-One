from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, DateField, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .analysis_statistics import procurement_analysis_statistics
from .models import ProcurementCase, ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_direct import DirectOpportunity
from .serializers import ProcurementNoticeListSerializer
from .views import NOTICE_RESULT_STAGES, NOTICE_SELECTED_STAGES, NOTICE_SUBMITTED_STAGES
from .views_recommended import latest_effective_recommended_notice_ids


SOURCE_PRIORITY = ("setad", "hezareh", "parsnamad")


def _multi_query_values(request, key: str) -> list[str]:
    """Accept repeated and comma-separated values while preserving old clients."""
    values = []
    for raw in request.query_params.getlist(key):
        values.extend(part.strip() for part in str(raw).split(","))
    return list(dict.fromkeys(value for value in values if value))


def _source_rank(source) -> tuple[int, str]:
    token = f"{source.key} {source.name}".casefold()
    if "setad" in token or "ستاد" in token:
        return 0, source.name
    if "hezareh" in token or "هزاره" in token:
        return 1, source.name
    if "parsnamad" in token or "پارس" in token:
        return 2, source.name
    return len(SOURCE_PRIORITY), source.name


class CompactNoticeSerializer(ProcurementNoticeListSerializer):
    sources = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    class Meta(ProcurementNoticeListSerializer.Meta):
        fields = ProcurementNoticeListSerializer.Meta.fields + ["sources"]

    def _ordered_source_notices(self, obj):
        items = [link.source_notice for link in obj.source_links.all()]
        items.sort(key=lambda item: (*_source_rank(item.connector.source), str(item.id)))
        unique = []
        seen = set()
        for item in items:
            key = str(item.connector.source_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _primary_source(self, obj):
        items = self._ordered_source_notices(obj)
        request = self.context.get("request")
        selected_name = ""
        if request is not None:
            selected_name = str(request.query_params.get("source_name", "")).strip().casefold()
        if selected_name:
            for item in items:
                if item.connector.source.name.casefold() == selected_name:
                    return item
        return items[0] if items else None

    def get_sources(self, obj):
        return [
            {
                "key": item.connector.source.key,
                "name": item.connector.source.name,
                "source_url": item.source_url,
                "detail_url": item.detail_url or item.source_url,
            }
            for item in self._ordered_source_notices(obj)
        ]

    def get_source_name(self, obj):
        item = self._primary_source(obj)
        return item.connector.source.name if item else ""

    def get_source_url(self, obj):
        item = self._primary_source(obj)
        return item.source_url if item else ""

    def get_detail_url(self, obj):
        item = self._primary_source(obj)
        return (item.detail_url or item.source_url) if item else ""


def _apply_search(queryset, value: str):
    value = value.strip()
    if not value:
        return queryset
    return queryset.filter(
        Q(reference_record__code__icontains=value)
        | Q(title__icontains=value)
        | Q(normalized_title__icontains=value)
        | Q(summary__icontains=value)
        | Q(description__icontains=value)
        | Q(employer_name__icontains=value)
        | Q(notice_number__icontains=value)
        | Q(province__icontains=value)
        | Q(city__icontains=value)
    )


def _apply_deadline_filters(queryset, request):
    now = timezone.now()
    in_24 = now + timedelta(hours=24)
    in_72 = now + timedelta(hours=72)
    in_168 = now + timedelta(hours=168)
    urgency_query = Q()
    for urgency in _multi_query_values(request, "urgency"):
        if urgency == "critical":
            urgency_query |= Q(submission_deadline__lt=in_24, submission_deadline__isnull=False)
        elif urgency == "high":
            urgency_query |= Q(submission_deadline__gte=in_24, submission_deadline__lte=in_72)
        elif urgency == "medium":
            urgency_query |= Q(submission_deadline__gt=in_72, submission_deadline__lte=in_168)
        elif urgency == "normal":
            urgency_query |= Q(submission_deadline__gt=in_168)
        elif urgency == "unknown":
            urgency_query |= Q(submission_deadline__isnull=True)
    if urgency_query:
        queryset = queryset.filter(urgency_query)

    deadline_query = Q()
    for deadline_status in _multi_query_values(request, "deadline_status"):
        if deadline_status == "expired":
            deadline_query |= Q(submission_deadline__lt=now)
        elif deadline_status == "expiring":
            deadline_query |= Q(submission_deadline__gte=now, submission_deadline__lte=in_72)
        elif deadline_status == "available":
            deadline_query |= Q(submission_deadline__gt=in_72)
        elif deadline_status == "unknown":
            deadline_query |= Q(submission_deadline__isnull=True)
    if deadline_query:
        queryset = queryset.filter(deadline_query)
    return queryset


def _compact_notice_queryset(request, *, force_recommended: bool = False):
    queryset = (
        ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
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
    notice_type = str(request.query_params.get("notice_type", "")).strip()
    if notice_type in {ProcurementNotice.NoticeType.TENDER, ProcurementNotice.NoticeType.INQUIRY}:
        queryset = queryset.filter(resolved_notice_type=notice_type)

    workflow = "recommended" if force_recommended else str(request.query_params.get("workflow", "recent")).strip()
    if workflow == "recommended":
        queryset = queryset.filter(
            pk__in=Subquery(latest_effective_recommended_notice_ids()),
            case__isnull=True,
        )
    elif workflow == "selected":
        queryset = queryset.filter(case__stage__in=NOTICE_SELECTED_STAGES)
    elif workflow == "submitted":
        queryset = queryset.filter(case__stage__in=NOTICE_SUBMITTED_STAGES)
    elif workflow == "results":
        queryset = queryset.filter(case__stage__in=NOTICE_RESULT_STAGES)
    else:
        start_date = timezone.localdate() - timedelta(days=2)
        queryset = queryset.filter(published_date__gte=start_date)

    source_names = _multi_query_values(request, "source_name")
    if source_names:
        source_query = Q()
        for source_name in source_names:
            token = source_name.casefold()
            if "ستاد" in token or "setad" in token:
                source_query |= Q(source_links__source_notice__connector__source__name__icontains="ستاد")
                source_query |= Q(source_links__source_notice__connector__source__key__icontains="setad")
            elif "هزاره" in token or "hezareh" in token:
                source_query |= Q(source_links__source_notice__connector__source__name__icontains="هزاره")
                source_query |= Q(source_links__source_notice__connector__source__key__icontains="hezareh")
            elif "پارس" in token or "parsnamad" in token:
                source_query |= Q(source_links__source_notice__connector__source__name__icontains="پارس")
                source_query |= Q(source_links__source_notice__connector__source__key__icontains="parsnamad")
            else:
                source_query |= Q(source_links__source_notice__connector__source__name=source_name)
        queryset = queryset.filter(source_query)
    province = str(request.query_params.get("province", "")).strip()
    if province:
        queryset = queryset.filter(province=province)
    importance = _multi_query_values(request, "importance")
    if importance:
        queryset = queryset.filter(importance__in=importance)

    published_on = str(request.query_params.get("published_on", "")).strip()
    if published_on:
        try:
            queryset = queryset.filter(published_date=date.fromisoformat(published_on))
        except ValueError:
            queryset = queryset.none()
    published_from = str(request.query_params.get("published_from", "")).strip()
    published_to = str(request.query_params.get("published_to", "")).strip()
    try:
        if published_from:
            queryset = queryset.filter(published_date__gte=date.fromisoformat(published_from))
        if published_to:
            queryset = queryset.filter(published_date__lte=date.fromisoformat(published_to))
    except ValueError:
        queryset = queryset.none()

    queryset = _apply_search(queryset, str(request.query_params.get("search", "")))
    queryset = _apply_deadline_filters(queryset, request)
    return queryset.distinct().order_by("-publication_sort", "-last_seen_at", "-id")


def _page_parameters(request):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get("page_size", 50))
    except (TypeError, ValueError):
        page_size = 50
    page_size = min(max(page_size, 1), 100)
    return page, page_size


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compact_notice_feed(request):
    queryset = _compact_notice_queryset(request)
    page, page_size = _page_parameters(request)
    count = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start:start + page_size])
    serializer = CompactNoticeSerializer(rows, many=True, context={"request": request})
    return Response(
        {
            "count": count,
            "page": page,
            "page_size": page_size,
            "next": None,
            "previous": None,
            "results": serializer.data,
        }
    )


def _type_counts(queryset, field: str) -> dict[str, int]:
    return {
        "total": queryset.count(),
        "tender": queryset.filter(**{field: ProcurementNotice.NoticeType.TENDER}).count(),
        "inquiry": queryset.filter(**{field: ProcurementNotice.NoticeType.INQUIRY}).count(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compact_dashboard(request):
    now = timezone.now()
    current_timezone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    today_start = timezone.make_aware(datetime.combine(today, time.min), current_timezone)
    tomorrow_start = today_start + timedelta(days=1)

    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False).exclude(
        processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED
    )
    analysis_stats = procurement_analysis_statistics()
    active_run = analysis_stats.get("active_run") or None
    if active_run:
        analysis_remaining = active_run.get("remaining") or {"total": 0, "tender": 0, "inquiry": 0}
        analysis_basis = "active_run_remaining"
    else:
        drafted_notice_ids = NoticeAnalysisDraft.objects.filter(
            notice__soft_deleted_at__isnull=True,
            notice__is_hidden=False,
        ).values("notice_id")
        remaining = notices.exclude(pk__in=Subquery(drafted_notice_ids))
        analysis_remaining = _type_counts(remaining, "resolved_notice_type")
        analysis_basis = "without_analysis_draft"

    cases = ProcurementCase.objects.select_related("notice", "responsible")
    selected_cases = cases.filter(stage__in=NOTICE_SELECTED_STAGES)
    submitted_cases = cases.filter(stage__in=NOTICE_SUBMITTED_STAGES)
    won_cases = cases.filter(stage=ProcurementCase.Stage.WON)
    near_deadline = notices.filter(
        submission_deadline__gte=now,
        submission_deadline__lte=now + timedelta(days=7),
    ).exclude(case__stage__in=NOTICE_RESULT_STAGES)
    today_notices = notices.filter(first_seen_at__gte=today_start, first_seen_at__lt=tomorrow_start)

    direct_active = DirectOpportunity.objects.filter(soft_deleted_at__isnull=True).exclude(
        stage__in=[
            DirectOpportunity.Stage.WON,
            DirectOpportunity.Stage.LOST,
            DirectOpportunity.Stage.STOPPED,
            DirectOpportunity.Stage.DEFERRED,
            DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        ]
    )

    return Response(
        {
            "generated_at": now,
            "metrics": {
                "all_notices": _type_counts(notices, "resolved_notice_type"),
                "new_today": _type_counts(today_notices, "resolved_notice_type"),
                "analysis_remaining": analysis_remaining,
                "recommended": analysis_stats.get("display_recommended") or {"total": 0, "tender": 0, "inquiry": 0},
                "selected": _type_counts(selected_cases, "notice__resolved_notice_type"),
                "submitted": _type_counts(submitted_cases, "notice__resolved_notice_type"),
                "near_deadline": _type_counts(near_deadline, "resolved_notice_type"),
                "successful_results": _type_counts(won_cases, "notice__resolved_notice_type"),
            },
            "management": {
                "overdue_actions": cases.exclude(stage__in=NOTICE_RESULT_STAGES).filter(next_action_due__lt=now).count(),
                "without_responsible": cases.exclude(stage__in=NOTICE_RESULT_STAGES).filter(responsible__isnull=True).count(),
                "direct_active": direct_active.count(),
            },
            "analysis": {
                "basis": analysis_basis,
                "run_id": active_run.get("id") if active_run else None,
                "run_status": active_run.get("status") if active_run else None,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_dismiss_recommendations(request):
    notice_type = str(request.query_params.get("notice_type", "")).strip()
    if notice_type not in {ProcurementNotice.NoticeType.TENDER, ProcurementNotice.NoticeType.INQUIRY}:
        return Response(
            {"detail": "نوع فراخوان برای حذف گروهی پیشنهادها باید مناقصه یا استعلام باشد."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    requested_ids = request.data.get("notice_ids") or []
    dismiss_all = bool(request.data.get("dismiss_all"))
    if not dismiss_all and not isinstance(requested_ids, list):
        return Response({"detail": "فهرست شناسه‌ها نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
    if not dismiss_all and not requested_ids:
        return Response({"detail": "هیچ پیشنهادی برای حذف گروهی انتخاب نشده است."}, status=status.HTTP_400_BAD_REQUEST)

    queryset = _compact_notice_queryset(request, force_recommended=True)
    if not dismiss_all:
        queryset = queryset.filter(pk__in=requested_ids)
    notice_ids = list(queryset.values_list("id", flat=True))
    if not notice_ids:
        return Response({"dismissed": 0, "notice_deleted": False})

    latest_drafts = []
    seen = set()
    for draft in NoticeAnalysisDraft.objects.filter(notice_id__in=notice_ids).order_by(
        "notice_id", "-analyzed_at", "-created_at", "-id"
    ).iterator(chunk_size=1000):
        if draft.notice_id in seen:
            continue
        seen.add(draft.notice_id)
        latest_drafts.append(draft)

    now = timezone.now()
    reason = str(request.data.get("reason", "حذف گروهی از فهرست پیشنهادی توسط کاربر")).strip()[:500]
    dismissed_notice_ids = [draft.notice_id for draft in latest_drafts]
    with transaction.atomic():
        for draft in latest_drafts:
            draft.review_status = NoticeAnalysisDraft.ReviewStatus.REJECTED
            draft.updated_at = now
        NoticeAnalysisDraft.objects.bulk_update(latest_drafts, ["review_status", "updated_at"], batch_size=500)
        ProcurementNotice.objects.filter(pk__in=dismissed_notice_ids).update(is_recommended=False)
        AuditEvent.objects.bulk_create(
            [
                AuditEvent(
                    actor=request.user.username,
                    action="procurement.ai_recommendation.dismiss_bulk",
                    target_type="procurement_notice",
                    target_id=str(draft.notice_id),
                    payload={
                        "analysis_draft_id": str(draft.id),
                        "review_status_after": NoticeAnalysisDraft.ReviewStatus.REJECTED,
                        "notice_deleted": False,
                        "reason": reason,
                    },
                )
                for draft in latest_drafts
            ],
            batch_size=500,
        )

    return Response(
        {
            "dismissed": len(dismissed_notice_ids),
            "notice_deleted": False,
            "scope": "all_filtered" if dismiss_all else "current_page",
        }
    )
