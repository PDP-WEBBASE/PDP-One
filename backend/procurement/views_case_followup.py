from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent

from .models import ProcurementCase
from .serializers import ProcurementCaseSerializer


def _staff_required(request):
    if not request.user or not request.user.is_authenticated or not request.user.is_staff:
        return Response({"detail": "مدیریت مسئولان و همکاران فقط برای مدیر سامانه مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    return None


def _latest_collaborators(case):
    event = AuditEvent.objects.filter(
        action="procurement.case.collaborators.set",
        target_type="procurement_case",
        target_id=str(case.id),
    ).order_by("-created_at").first()
    return list((event.payload or {}).get("collaborator_usernames", [])) if event else []


def _notes(case, limit=20):
    events = AuditEvent.objects.filter(
        action="procurement.case.follow_up_note",
        target_type="procurement_case",
        target_id=str(case.id),
    ).order_by("-created_at")[:limit]
    return [
        {
            "id": str(event.id),
            "author": event.actor,
            "text": str((event.payload or {}).get("text", "")),
            "created_at": event.created_at,
        }
        for event in events
    ]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def follow_up_users(request):
    users = get_user_model().objects.filter(is_active=True).order_by("username")
    return Response([{"id": user.id, "username": user.username, "is_staff": user.is_staff} for user in users])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def follow_up_summary(request):
    now = timezone.now()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    week_end = today_end + timedelta(days=7)
    active = ProcurementCase.objects.select_related("notice", "responsible").exclude(
        stage__in=[
            ProcurementCase.Stage.LOST,
            ProcurementCase.Stage.CANCELLED,
            ProcurementCase.Stage.DO_NOT_PARTICIPATE,
        ]
    )
    responsible = str(request.query_params.get("responsible", "")).strip()
    if responsible:
        active = active.filter(responsible__username=responsible)

    def pack(queryset):
        return [
            {
                **ProcurementCaseSerializer(case).data,
                "notice_title": case.notice.title,
                "notice_employer_name": case.notice.employer_name,
                "collaborator_usernames": _latest_collaborators(case),
            }
            for case in queryset[:100]
        ]

    overdue = active.filter(next_action_due__lt=now).order_by("next_action_due")
    today = active.filter(next_action_due__gte=now, next_action_due__lte=today_end).order_by("next_action_due")
    week = active.filter(next_action_due__gt=today_end, next_action_due__lte=week_end).order_by("next_action_due")
    no_due = active.filter(next_action_due__isnull=True).order_by("-updated_at")
    return Response({
        "generated_at": now,
        "overdue_count": overdue.count(),
        "today_count": today.count(),
        "week_count": week.count(),
        "no_due_count": no_due.count(),
        "overdue": pack(overdue),
        "today": pack(today),
        "week": pack(week),
        "no_due": pack(no_due),
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def case_follow_up(request, case_id):
    case = get_object_or_404(ProcurementCase.objects.select_related("notice", "responsible"), pk=case_id)
    if request.method == "GET":
        return Response({
            "case": ProcurementCaseSerializer(case).data,
            "notice_title": case.notice.title,
            "notice_employer_name": case.notice.employer_name,
            "collaborator_usernames": _latest_collaborators(case),
            "notes": _notes(case),
        })

    denied = _staff_required(request)
    if denied:
        return denied
    usernames = request.data.get("collaborator_usernames", [])
    if not isinstance(usernames, list):
        return Response({"detail": "فهرست همکاران نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)
    normalized = sorted({str(item).strip() for item in usernames if str(item).strip()})
    existing_users = set(get_user_model().objects.filter(username__in=normalized, is_active=True).values_list("username", flat=True))
    missing = sorted(set(normalized) - existing_users)
    if missing:
        return Response({"detail": "برخی همکاران در سامانه وجود ندارند.", "missing": missing}, status=status.HTTP_400_BAD_REQUEST)

    responsible_username = str(request.data.get("responsible_username", "")).strip()
    if responsible_username:
        try:
            responsible = get_user_model().objects.get(username=responsible_username, is_active=True)
        except get_user_model().DoesNotExist:
            return Response({"detail": "مسئول انتخاب‌شده در سامانه وجود ندارد."}, status=status.HTTP_400_BAD_REQUEST)
        case.responsible = responsible
    if "next_action" in request.data:
        case.next_action = str(request.data.get("next_action", "")).strip()[:500]
    if "next_action_due" in request.data:
        case.next_action_due = request.data.get("next_action_due") or None
    case.save(update_fields=["responsible", "next_action", "next_action_due", "updated_at"])

    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.case.collaborators.set",
        target_type="procurement_case",
        target_id=str(case.id),
        payload={
            "responsible_username": case.responsible.username if case.responsible else "",
            "collaborator_usernames": normalized,
            "next_action": case.next_action,
            "next_action_due": case.next_action_due.isoformat() if case.next_action_due else None,
        },
    )
    note = str(request.data.get("note", "")).strip()[:2000]
    if note:
        AuditEvent.objects.create(
            actor=request.user.username,
            action="procurement.case.follow_up_note",
            target_type="procurement_case",
            target_id=str(case.id),
            payload={"text": note},
        )
    return Response({
        "case": ProcurementCaseSerializer(case).data,
        "notice_title": case.notice.title,
        "notice_employer_name": case.notice.employer_name,
        "collaborator_usernames": normalized,
        "notes": _notes(case),
    })
