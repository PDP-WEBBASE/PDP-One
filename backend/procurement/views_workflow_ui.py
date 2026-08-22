from uuid import UUID

from django.db.models import Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ProcurementCase
from .models_direct import DirectOpportunity


MAX_PAGE_IDS = 100


def _uuid_list(raw_value: str):
    values = []
    seen = set()
    for token in str(raw_value or "").split(","):
        token = token.strip()
        if not token or token in seen:
            continue
        try:
            UUID(token)
        except (TypeError, ValueError):
            continue
        seen.add(token)
        values.append(token)
        if len(values) >= MAX_PAGE_IDS:
            break
    return values


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workflow_page_metadata(request):
    """Return only action metadata for records already present on the current UI page.

    This endpoint intentionally accepts at most one page (100 IDs). It replaces the
    legacy browser behavior that scanned many workflow pages and then fetched one
    notice detail per case merely to decorate the visible rows.
    """

    notice_ids = _uuid_list(request.query_params.get("notice_ids", ""))
    direct_ids = _uuid_list(request.query_params.get("direct_ids", ""))

    cases = []
    if notice_ids:
        rows = (
            ProcurementCase.objects.filter(notice_id__in=notice_ids)
            .annotate(submission_document_count=Count("submission_documents"))
            .values(
                "id",
                "notice_id",
                "stage",
                "submission_document_count",
            )
        )
        cases = [
            {
                "id": str(row["id"]),
                "notice_id": str(row["notice_id"]),
                "stage": row["stage"],
                "submission_document_count": int(row["submission_document_count"] or 0),
            }
            for row in rows
        ]

    direct_documents = {}
    if direct_ids:
        rows = (
            DirectOpportunity.objects.filter(
                id__in=direct_ids,
                soft_deleted_at__isnull=True,
            )
            .annotate(submission_document_count=Count("submission_documents"))
            .values("id", "submission_document_count")
        )
        direct_documents = {
            str(row["id"]): int(row["submission_document_count"] or 0)
            for row in rows
        }

    return Response(
        {
            "cases": cases,
            "direct_documents": direct_documents,
            "notice_ids_requested": len(notice_ids),
            "direct_ids_requested": len(direct_ids),
        }
    )
