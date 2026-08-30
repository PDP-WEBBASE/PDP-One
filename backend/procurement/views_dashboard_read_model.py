from datetime import datetime, time, timedelta

from django.core.cache import cache
from django.db.models import Count, Q, Subquery
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_run_service import active_run
from .models import ProcurementCase, ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_analysis_runs import ProcurementAnalysisRunItem
from .models_direct import DirectOpportunity
from .performance_metrics import instrument_procurement_endpoint
from .views import NOTICE_RESULT_STAGES, NOTICE_SELECTED_STAGES, NOTICE_SUBMITTED_STAGES
from .views_recommended import latest_effective_recommended_notice_ids

DASHBOARD_CACHE_KEY = "pdp:procurement:dashboard-read-model:v2"
DASHBOARD_CACHE_TTL_SECONDS = 20

OPEN_ANALYSIS_ITEM_STATUSES = [
    ProcurementAnalysisRunItem.Status.PENDING,
    ProcurementAnalysisRunItem.Status.CLAIMED,
    ProcurementAnalysisRunItem.Status.SCREENED,
    ProcurementAnalysisRunItem.Status.WAITING_DEEP_ANALYSIS,
    ProcurementAnalysisRunItem.Status.RETRY,
]


def _breakdown(values: dict, prefix: str) -> dict[str, int]:
    return {
        "total": int(values.get(f"{prefix}_total") or 0),
        "tender": int(values.get(f"{prefix}_tender") or 0),
        "inquiry": int(values.get(f"{prefix}_inquiry") or 0),
    }


def _typed_count_fields(prefix: str, field: str, extra_filter: Q | None = None) -> dict:
    base = extra_filter or Q()
    return {
        f"{prefix}_total": Count("pk", filter=base),
        f"{prefix}_tender": Count(
            "pk",
            filter=base & Q(**{field: ProcurementNotice.NoticeType.TENDER}),
        ),
        f"{prefix}_inquiry": Count(
            "pk",
            filter=base & Q(**{field: ProcurementNotice.NoticeType.INQUIRY}),
        ),
    }


def _analysis_remaining(run, notices) -> dict[str, int]:
    """Return a truthful analysis backlog with at most one cold-path aggregate.

    Active persistent runs use their persisted counters when a truthful by-type
    split is available, otherwise one grouped aggregate over the indexed
    run/status relation. When there is no active persistent run, the dashboard
    falls back to notices without an analysis draft rather than reporting a
    false zero. The whole dashboard payload is protected by the short shared
    cache, so the fallback does not become a per-render query storm.
    """

    if run is None:
        drafted_notice_ids = NoticeAnalysisDraft.objects.filter(
            notice__soft_deleted_at__isnull=True,
            notice__is_hidden=False,
        ).values("notice_id")
        remaining = notices.exclude(pk__in=Subquery(drafted_notice_ids))
        values = remaining.aggregate(
            **_typed_count_fields("remaining", "resolved_notice_type")
        )
        return _breakdown(values, "remaining")

    counters = run.counters or {}
    persisted = counters.get("remaining_by_type") or {}
    tender = int(persisted.get("tender", 0) or 0)
    inquiry = int(persisted.get("inquiry", 0) or 0)
    total = int(counters.get("remaining", tender + inquiry) or 0)
    if tender + inquiry == total and (total == 0 or tender or inquiry):
        return {"total": total, "tender": tender, "inquiry": inquiry}

    counts = run.items.filter(status__in=OPEN_ANALYSIS_ITEM_STATUSES).aggregate(
        total=Count("pk"),
        tender=Count("pk", filter=Q(notice__resolved_notice_type=ProcurementNotice.NoticeType.TENDER)),
        inquiry=Count("pk", filter=Q(notice__resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY)),
    )
    return {
        "total": int(counts.get("total") or 0),
        "tender": int(counts.get("tender") or 0),
        "inquiry": int(counts.get("inquiry") or 0),
    }


def _active_case_projection(cases, direct_items):
    rows = []
    for case in cases.select_related("notice")[:20]:
        notice = case.notice
        rows.append(
            {
                "id": str(notice.id),
                "title": notice.title,
                "subtitle": f"{notice.get_resolved_notice_type_display()} · {notice.employer_name or 'کارفرما نامشخص'}",
                "stage": case.get_stage_display(),
                "deadline": notice.submission_deadline,
                "kind": "notice",
            }
        )
    remaining = max(0, 20 - len(rows))
    if remaining:
        for item in direct_items[:remaining]:
            rows.append(
                {
                    "id": str(item.id),
                    "title": item.title,
                    "subtitle": f"ارجاع مستقیم · {item.employer_name or 'کارفرما نامشخص'}",
                    "stage": item.get_stage_display(),
                    "deadline": item.next_action_due,
                    "kind": "direct",
                }
            )
    return rows


def _dashboard_payload():
    now = timezone.now()
    current_timezone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    today_start = timezone.make_aware(datetime.combine(today, time.min), current_timezone)
    tomorrow_start = today_start + timedelta(days=1)

    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False).exclude(
        processing_status=ProcurementNotice.ProcessingStatus.RETENTION_CLEANED
    )
    near_filter = Q(
        submission_deadline__gte=now,
        submission_deadline__lte=now + timedelta(days=7),
    ) & ~Q(case__stage__in=NOTICE_RESULT_STAGES)
    today_filter = Q(first_seen_at__gte=today_start, first_seen_at__lt=tomorrow_start)
    notice_counts = notices.aggregate(
        **_typed_count_fields("all", "resolved_notice_type"),
        **_typed_count_fields("today", "resolved_notice_type", today_filter),
        **_typed_count_fields("near", "resolved_notice_type", near_filter),
    )

    recommended = notices.filter(pk__in=Subquery(latest_effective_recommended_notice_ids())).aggregate(
        **_typed_count_fields("recommended", "resolved_notice_type")
    )

    cases = ProcurementCase.objects.all()
    selected_filter = Q(stage__in=NOTICE_SELECTED_STAGES)
    submitted_filter = Q(stage__in=NOTICE_SUBMITTED_STAGES)
    won_filter = Q(stage=ProcurementCase.Stage.WON)
    lost_filter = Q(stage=ProcurementCase.Stage.LOST)
    case_counts = cases.aggregate(
        **_typed_count_fields("selected", "notice__resolved_notice_type", selected_filter),
        **_typed_count_fields("submitted", "notice__resolved_notice_type", submitted_filter),
        **_typed_count_fields("won", "notice__resolved_notice_type", won_filter),
        **_typed_count_fields("lost", "notice__resolved_notice_type", lost_filter),
        overdue_actions=Count(
            "pk",
            filter=~Q(stage__in=NOTICE_RESULT_STAGES) & Q(next_action_due__lt=now),
        ),
        without_responsible=Count(
            "pk",
            filter=~Q(stage__in=NOTICE_RESULT_STAGES) & Q(responsible__isnull=True),
        ),
    )

    active_cases = cases.filter(
        stage__in=NOTICE_SELECTED_STAGES + NOTICE_SUBMITTED_STAGES
    ).order_by("next_action_due", "id")

    terminal_direct_stages = [
        DirectOpportunity.Stage.WON,
        DirectOpportunity.Stage.LOST,
        DirectOpportunity.Stage.STOPPED,
        DirectOpportunity.Stage.DEFERRED,
        DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
        DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
    ]
    direct_all = DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)
    direct_counts = direct_all.aggregate(
        direct_total=Count("pk"),
        direct_active=Count("pk", filter=~Q(stage__in=terminal_direct_stages)),
    )
    direct_case_items = direct_all.filter(
        stage__in=[
            DirectOpportunity.Stage.SELECTED,
            DirectOpportunity.Stage.PREPARING,
            DirectOpportunity.Stage.SUBMITTED,
        ]
    ).order_by("next_action_due", "id")

    run = active_run()
    analysis_remaining = _analysis_remaining(run, notices)

    return {
        "generated_at": now,
        "metrics": {
            "all_notices": _breakdown(notice_counts, "all"),
            "new_today": _breakdown(notice_counts, "today"),
            "analysis_remaining": analysis_remaining,
            "recommended": _breakdown(recommended, "recommended"),
            "selected": _breakdown(case_counts, "selected"),
            "submitted": _breakdown(case_counts, "submitted"),
            "near_deadline": _breakdown(notice_counts, "near"),
            "successful_results": _breakdown(case_counts, "won"),
            "unsuccessful_results": _breakdown(case_counts, "lost"),
        },
        "management": {
            "overdue_actions": int(case_counts.get("overdue_actions") or 0),
            "without_responsible": int(case_counts.get("without_responsible") or 0),
            "direct_active": int(direct_counts.get("direct_active") or 0),
            "direct_total": int(direct_counts.get("direct_total") or 0),
        },
        "active_cases": _active_case_projection(active_cases, direct_case_items),
        "analysis": {
            "basis": "persisted_run_counters_or_bounded_split" if run else "without_analysis_draft",
            "run_id": str(run.id) if run else None,
            "run_status": run.status if run else None,
        },
    }


@instrument_procurement_endpoint("procurement.ui.dashboard.v2")
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compact_dashboard_read_model(request):
    """Low-latency dashboard read model with a short shared snapshot cache."""

    payload = cache.get(DASHBOARD_CACHE_KEY)
    if payload is None:
        payload = _dashboard_payload()
        cache.set(DASHBOARD_CACHE_KEY, payload, DASHBOARD_CACHE_TTL_SECONDS)
    return Response(payload)
