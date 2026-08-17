from datetime import timedelta

from django.db.models import BooleanField, Case, F, Subquery, Value, When, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ProcurementCase, ProcurementNotice
from .models_analysis import NoticeAnalysisDraft
from .models_direct import DirectOpportunity


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


def _latest_effective_recommended_ids():
    return (
        NoticeAnalysisDraft.objects.annotate(
            recommendation_rank=Window(
                expression=RowNumber(),
                partition_by=[F("notice_id")],
                order_by=[F("analyzed_at").desc(), F("created_at").desc(), F("id").desc()],
            ),
            effective_recommendation=Case(
                When(review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED, then=Value(False)),
                default=F("is_recommended"),
                output_field=BooleanField(),
            ),
        )
        .filter(recommendation_rank=1, effective_recommendation=True)
        .values("notice_id")
    )


@api_view(["GET"])
def pagination_dashboard_metrics(request):
    """Exact aggregate counts used when browser collections are page-bounded.

    This endpoint intentionally returns counts only. It prevents the dashboard
    from depending on a full browser-side copy of the procurement archive.
    """

    now = timezone.now()
    within_72_hours = now + timedelta(hours=72)
    notices = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
    cases = ProcurementCase.objects.all()
    direct = DirectOpportunity.objects.filter(soft_deleted_at__isnull=True)

    effective_recommended = notices.filter(pk__in=Subquery(_latest_effective_recommended_ids())).count()
    direct_recommended = direct.filter(stage__in=DIRECT_RECOMMENDED_STAGES).count()
    selected = cases.filter(stage__in=NOTICE_SELECTED_STAGES).count() + direct.filter(stage__in=DIRECT_SELECTED_STAGES).count()
    submitted = cases.filter(stage__in=NOTICE_SUBMITTED_STAGES).count() + direct.filter(stage=DirectOpportunity.Stage.SUBMITTED).count()
    urgent = (
        notices.filter(submission_deadline__isnull=False, submission_deadline__lte=within_72_hours)
        .exclude(case__stage__in=NOTICE_RESULT_STAGES)
        .count()
    )
    won = cases.filter(stage=ProcurementCase.Stage.WON).count() + direct.filter(
        stage__in=[DirectOpportunity.Stage.WON, DirectOpportunity.Stage.CONVERTED_TO_CONTRACT]
    ).count()
    lost = cases.filter(stage=ProcurementCase.Stage.LOST).count() + direct.filter(stage=DirectOpportunity.Stage.LOST).count()

    return Response(
        {
            "notice_total": notices.count(),
            "unanalyzed": notices.exclude(processing_status=ProcurementNotice.ProcessingStatus.ANALYZED).count(),
            "recommended": effective_recommended + direct_recommended,
            "selected": selected,
            "submitted": submitted,
            "urgent": urgent,
            "won": won,
            "lost": lost,
            "win_rate": round((won / (won + lost)) * 100) if won + lost else 0,
        }
    )
