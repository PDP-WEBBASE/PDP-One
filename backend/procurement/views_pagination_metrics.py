from datetime import timedelta

from django.db.models import Subquery
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .analysis_run_service import OPEN_ITEM_STATUSES, active_run
from .models import ProcurementCase, ProcurementNotice
from .models_direct import DirectOpportunity
from .views_recommended import latest_effective_recommended_notice_ids


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
DIRECT_RECOMMENDED_STAGES = [
    DirectOpportunity.Stage.REVIEWING,
    DirectOpportunity.Stage.FOLLOWING_UP,
    DirectOpportunity.Stage.NEGOTIATING,
]
DIRECT_SELECTED_STAGES = [
    DirectOpportunity.Stage.SELECTED,
    DirectOpportunity.Stage.PREPARING,
]


def _type_counts(queryset, field_name):
    return {
        "total": queryset.count(),
        "tender": queryset.filter(**{field_name: ProcurementNotice.NoticeType.TENDER}).count(),
        "inquiry": queryset.filter(**{field_name: ProcurementNotice.NoticeType.INQUIRY}).count(),
    }


@api_view(["GET"])
def pagination_dashboard_metrics(request):
    """Exact database-side counts for the compact management dashboard.

    Browser pagination must never be used as the source for global KPI values.
    When a persistent analysis run is active, its open-item set is the same basis
    used by the analysis engine and is therefore the preferred backlog measure.
    """

    now = timezone.now()
    today = timezone.localdate(now)
    within_72_hours = now + timedelta(hours=72)
    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
    cases = ProcurementCase.objects.select_related("notice")
    direct = DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)

    recommended_notices = notices.filter(pk__in=Subquery(latest_effective_recommended_notice_ids()))
    selected_cases = cases.filter(stage__in=NOTICE_SELECTED_STAGES)
    submitted_cases = cases.filter(stage__in=NOTICE_SUBMITTED_STAGES)
    urgent_notices = (
        notices.filter(
            submission_deadline__isnull=False,
            submission_deadline__gte=now,
            submission_deadline__lte=within_72_hours,
        )
        .exclude(case__stage__in=NOTICE_RESULT_STAGES)
    )
    won_cases = cases.filter(stage=ProcurementCase.Stage.WON)
    lost_cases = cases.filter(stage=ProcurementCase.Stage.LOST)
    new_today = notices.filter(first_seen_at__date=today)

    current_run = active_run()
    if current_run is not None:
        analysis_backlog = current_run.items.filter(status__in=OPEN_ITEM_STATUSES)
        analysis_breakdown = _type_counts(analysis_backlog, "notice__resolved_notice_type")
        analysis_basis = "active_run_remaining"
        analysis_run_id = str(current_run.id)
    else:
        fallback_backlog = notices.exclude(processing_status=ProcurementNotice.ProcessingStatus.ANALYZED)
        analysis_breakdown = _type_counts(fallback_backlog, "resolved_notice_type")
        analysis_basis = "processing_status_fallback"
        analysis_run_id = None

    notice_total_breakdown = _type_counts(notices, "resolved_notice_type")
    recommended_breakdown = _type_counts(recommended_notices, "resolved_notice_type")
    selected_breakdown = _type_counts(selected_cases, "notice__resolved_notice_type")
    submitted_breakdown = _type_counts(submitted_cases, "notice__resolved_notice_type")
    urgent_breakdown = _type_counts(urgent_notices, "resolved_notice_type")
    won_breakdown = _type_counts(won_cases, "notice__resolved_notice_type")
    lost_breakdown = _type_counts(lost_cases, "notice__resolved_notice_type")
    new_today_breakdown = _type_counts(new_today, "resolved_notice_type")

    direct_recommended = direct.filter(stage__in=DIRECT_RECOMMENDED_STAGES).count()
    direct_selected = direct.filter(stage__in=DIRECT_SELECTED_STAGES).count()
    direct_submitted = direct.filter(stage=DirectOpportunity.Stage.SUBMITTED).count()
    direct_won = direct.filter(
        stage__in=[DirectOpportunity.Stage.WON, DirectOpportunity.Stage.CONVERTED_TO_CONTRACT]
    ).count()
    direct_lost = direct.filter(stage=DirectOpportunity.Stage.LOST).count()
    direct_active = direct.exclude(
        stage__in=[
            DirectOpportunity.Stage.WON,
            DirectOpportunity.Stage.LOST,
            DirectOpportunity.Stage.STOPPED,
            DirectOpportunity.Stage.DEFERRED,
            DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
            DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        ]
    ).count()

    legacy_selected = selected_breakdown["total"] + direct_selected
    legacy_submitted = submitted_breakdown["total"] + direct_submitted
    legacy_won = won_breakdown["total"] + direct_won
    legacy_lost = lost_breakdown["total"] + direct_lost

    return Response(
        {
            # Stable scalar fields retained for older dashboard enhancement layers.
            "notice_total": notice_total_breakdown["total"],
            "unanalyzed": analysis_breakdown["total"],
            "recommended": recommended_breakdown["total"] + direct_recommended,
            "selected": legacy_selected,
            "submitted": legacy_submitted,
            "urgent": urgent_breakdown["total"],
            "won": legacy_won,
            "lost": legacy_lost,
            "win_rate": round((legacy_won / (legacy_won + legacy_lost)) * 100) if legacy_won + legacy_lost else 0,
            # New compact dashboard contract: total notice value plus tender/inquiry split.
            "breakdown": {
                "notice_total": notice_total_breakdown,
                "new_today": new_today_breakdown,
                "unanalyzed": analysis_breakdown,
                "recommended": recommended_breakdown,
                "selected": selected_breakdown,
                "submitted": submitted_breakdown,
                "urgent": urgent_breakdown,
                "won": won_breakdown,
                "lost": lost_breakdown,
            },
            "analysis_basis": analysis_basis,
            "analysis_run_id": analysis_run_id,
            "direct": {
                "active": direct_active,
                "recommended": direct_recommended,
                "selected": direct_selected,
                "submitted": direct_submitted,
                "won": direct_won,
                "lost": direct_lost,
            },
        }
    )
