from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Subquery
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_statistics import procurement_analysis_statistics
from .models import ProcurementCase, ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_direct import DirectOpportunity
from .performance_metrics import instrument_procurement_endpoint
from .views import NOTICE_RESULT_STAGES, NOTICE_SELECTED_STAGES, NOTICE_SUBMITTED_STAGES


def _type_counts(queryset, field: str) -> dict[str, int]:
    """Return total/tender/inquiry in one aggregate query instead of three counts."""

    values = queryset.aggregate(
        total=Count("pk"),
        tender=Count("pk", filter=Q(**{field: ProcurementNotice.NoticeType.TENDER})),
        inquiry=Count("pk", filter=Q(**{field: ProcurementNotice.NoticeType.INQUIRY})),
    )
    return {key: int(values.get(key) or 0) for key in ("total", "tender", "inquiry")}


@instrument_procurement_endpoint("procurement.ui.dashboard.v1")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compact_dashboard_read_model(request):
    """Compatibility-preserving dashboard projection with bounded count-query fanout."""

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

    cases = ProcurementCase.objects.all()
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
