import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .models import ProcurementCase, ProcurementNotice
from .views import NOTICE_SELECTED_STAGES
from .views_compact_ui import CompactNoticeSerializer, _compact_notice_queryset, _page_parameters


VIEW_DISMISS_ACTION = "procurement.workflow.dismiss_from_view"
VIEW_DISMISS_WORKFLOWS = {"recent", "submitted", "results"}
BULK_REMOVE_WORKFLOWS = {"selected", *VIEW_DISMISS_WORKFLOWS}
MAX_BULK_IDS = 100


def _normalized_notice_ids(values):
    if not isinstance(values, list):
        return None
    normalized = []
    seen = set()
    for value in values:
        try:
            token = str(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            return None
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _user_dismissed_notice_ids(request, workflow: str):
    if workflow not in VIEW_DISMISS_WORKFLOWS:
        return []
    return list(
        AuditEvent.objects.filter(
            actor=request.user.username,
            action=VIEW_DISMISS_ACTION,
            target_type="procurement_notice",
            payload__workflow=workflow,
        ).values_list("target_id", flat=True)
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compact_notice_feed_with_dismissals(request):
    """Stable compact notice feed with user-scoped list dismissals applied.

    A dismissal hides a notice only from the requested Recent/Submitted/Results
    workflow for the current user. It never deletes the notice, analysis history,
    submission documents, or result data.
    """

    queryset = _compact_notice_queryset(request)
    workflow = str(request.query_params.get("workflow", "recent")).strip() or "recent"
    dismissed_ids = _user_dismissed_notice_ids(request, workflow)
    if dismissed_ids:
        queryset = queryset.exclude(pk__in=dismissed_ids)

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_remove_workflow_items(request):
    """Remove selected current-page rows from one procurement workflow safely.

    Selected uses the existing guarded pre-submission case-removal semantics.
    Recent/Submitted/Results are view-only dismissals recorded in AuditEvent so
    business stage, documents, result evidence, notices and AI history remain
    untouched.
    """

    notice_type = str(request.query_params.get("notice_type", "")).strip()
    if notice_type not in {ProcurementNotice.NoticeType.TENDER, ProcurementNotice.NoticeType.INQUIRY}:
        return Response(
            {"detail": "نوع فراخوان برای حذف گروهی باید مناقصه یا استعلام باشد."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    workflow = str(request.query_params.get("workflow", "")).strip()
    if workflow not in BULK_REMOVE_WORKFLOWS:
        return Response(
            {"detail": "این گردش‌کار برای حذف گروهی امن پشتیبانی نمی‌شود."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    requested_ids = _normalized_notice_ids(request.data.get("notice_ids"))
    if requested_ids is None:
        return Response({"detail": "فهرست شناسه‌ها نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
    if not requested_ids:
        return Response({"detail": "هیچ ردیفی برای حذف گروهی انتخاب نشده است."}, status=status.HTTP_400_BAD_REQUEST)
    if len(requested_ids) > MAX_BULK_IDS:
        return Response(
            {"detail": f"حذف گروهی در هر درخواست حداکثر برای {MAX_BULK_IDS} ردیف مجاز است."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = _compact_notice_queryset(request).filter(pk__in=requested_ids)
    valid_ids = [str(item) for item in queryset.values_list("id", flat=True)]
    if not valid_ids:
        return Response({"removed": 0, "blocked": 0, "notice_deleted": False})

    reason = str(request.data.get("reason", "حذف گروهی از فهرست توسط کاربر")).strip()[:500]

    if workflow == "selected":
        removed = 0
        blocked = 0
        removed_notice_ids = []
        audit_events = []
        cases = list(
            ProcurementCase.objects.filter(
                notice_id__in=valid_ids,
                stage__in=NOTICE_SELECTED_STAGES,
            ).prefetch_related("submission_documents")
        )
        with transaction.atomic():
            for case in cases:
                if case.submission_documents.exists():
                    blocked += 1
                    continue
                notice_id = case.notice_id
                case_id = str(case.id)
                stage_before = case.stage
                case.delete()
                removed += 1
                removed_notice_ids.append(notice_id)
                audit_events.append(
                    AuditEvent(
                        actor=request.user.username,
                        action="procurement.case.remove_from_selected_bulk",
                        target_type="procurement_case",
                        target_id=case_id,
                        payload={
                            "notice_id": str(notice_id),
                            "stage_before": stage_before,
                            "notice_deleted": False,
                            "reason": reason,
                        },
                    )
                )
            if removed_notice_ids:
                ProcurementNotice.objects.filter(pk__in=removed_notice_ids).update(retention_protected=False)
            if audit_events:
                AuditEvent.objects.bulk_create(audit_events, batch_size=100)
        return Response(
            {
                "removed": removed,
                "blocked": blocked,
                "notice_deleted": False,
                "mode": "remove_selected_case",
            }
        )

    existing = set(
        AuditEvent.objects.filter(
            actor=request.user.username,
            action=VIEW_DISMISS_ACTION,
            target_type="procurement_notice",
            target_id__in=valid_ids,
            payload__workflow=workflow,
        ).values_list("target_id", flat=True)
    )
    new_ids = [notice_id for notice_id in valid_ids if notice_id not in existing]
    if new_ids:
        AuditEvent.objects.bulk_create(
            [
                AuditEvent(
                    actor=request.user.username,
                    action=VIEW_DISMISS_ACTION,
                    target_type="procurement_notice",
                    target_id=notice_id,
                    payload={
                        "workflow": workflow,
                        "notice_type": notice_type,
                        "notice_deleted": False,
                        "business_stage_changed": False,
                        "reason": reason,
                    },
                )
                for notice_id in new_ids
            ],
            batch_size=100,
        )

    return Response(
        {
            "removed": len(new_ids),
            "blocked": 0,
            "notice_deleted": False,
            "business_stage_changed": False,
            "mode": "view_dismissal",
        }
    )
