from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Contract

from .analysis_review import analysis_review_summary
from .models import ProcurementCase, ProcurementNotice
from .models_extraction import ExtractionRun


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unified_management_dashboard(request):
    now = timezone.now()
    cases = ProcurementCase.objects.select_related("notice", "responsible")
    case_by_stage = {row["stage"]: row["count"] for row in cases.values("stage").annotate(count=Count("id"))}
    submitted = case_by_stage.get(ProcurementCase.Stage.SUBMITTED, 0) + case_by_stage.get(ProcurementCase.Stage.AWAITING_RESULT, 0)
    won = case_by_stage.get(ProcurementCase.Stage.WON, 0)
    lost = case_by_stage.get(ProcurementCase.Stage.LOST, 0)
    decided = won + lost
    overdue = cases.exclude(
        stage__in=[ProcurementCase.Stage.LOST, ProcurementCase.Stage.CANCELLED, ProcurementCase.Stage.DO_NOT_PARTICIPATE]
    ).filter(next_action_due__lt=now).count()

    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True)
    notice_by_type = {row["resolved_notice_type"]: row["count"] for row in notices.values("resolved_notice_type").annotate(count=Count("id"))}
    contract_totals = Contract.objects.aggregate(total_value=Sum("value_rials"))
    case_contracts = Contract.objects.filter(code__startswith="CASE-")
    latest_runs = [
        {
            "id": str(run.id),
            "connector_keys": list(run.connectors.values_list("key", flat=True)),
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "records_new": run.records_new,
            "records_updated": run.records_updated,
            "records_failed": run.records_failed,
        }
        for run in ExtractionRun.objects.prefetch_related("connectors").order_by("-created_at")[:20]
    ]

    return Response({
        "generated_at": now,
        "notices": {
            "total": notices.count(),
            "recommended": notices.filter(is_recommended=True).count(),
            "selected": cases.count(),
            "by_type": notice_by_type,
        },
        "analysis_review": analysis_review_summary(),
        "cases": {
            "total": cases.count(),
            "by_stage": case_by_stage,
            "submitted_or_awaiting": submitted,
            "won": won,
            "lost": lost,
            "win_rate_percent": round((won / decided) * 100, 2) if decided else 0,
            "overdue": overdue,
            "without_responsible": cases.filter(responsible__isnull=True).count(),
        },
        "contracts": {
            "total": Contract.objects.count(),
            "draft": Contract.objects.filter(status=Contract.Status.DRAFT).count(),
            "active": Contract.objects.filter(status=Contract.Status.ACTIVE).count(),
            "case_generated_drafts": case_contracts.filter(status=Contract.Status.DRAFT).count(),
            "total_value_rials": contract_totals["total_value"] or 0,
            "case_generated_value_rials": case_contracts.aggregate(total=Sum("value_rials"))["total"] or 0,
        },
        "latest_extraction_runs": latest_runs,
        "uses_live_data_only": True,
    })
