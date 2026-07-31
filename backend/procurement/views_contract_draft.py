from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditEvent, Contract
from core.serializers import ContractSerializer

from .models import ProcurementCase


def _staff_required(request):
    if not request.user or not request.user.is_authenticated or not request.user.is_staff:
        return Response({"detail": "ایجاد پیش‌نویس قرارداد فقط برای مدیر سامانه مجاز است."}, status=status.HTTP_403_FORBIDDEN)
    return None


def _contract_code(case):
    return f"CASE-{case.id.hex[:12].upper()}"


def _proposal(case):
    notice = case.notice
    return {
        "code": _contract_code(case),
        "title": notice.title,
        "employer": notice.employer_name or "کارفرما درج نشده",
        "field": "",
        "value_rials": notice.estimated_amount_rials,
        "progress": 0,
        "due_date": None,
        "status": Contract.Status.DRAFT,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def contract_draft_preview(request, case_id):
    case = get_object_or_404(ProcurementCase.objects.select_related("notice"), pk=case_id)
    code = _contract_code(case)
    existing = Contract.objects.filter(code=code).first()
    return Response({
        "eligible": case.stage == ProcurementCase.Stage.WON,
        "case_id": str(case.id),
        "case_stage": case.stage,
        "case_stage_label": case.get_stage_display(),
        "notice_id": str(case.notice_id),
        "proposal": _proposal(case),
        "existing_contract": ContractSerializer(existing).data if existing else None,
        "requires_explicit_confirmation": True,
        "creates_financial_records": False,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def create_contract_draft_from_case(request, case_id):
    denied = _staff_required(request)
    if denied:
        return denied
    case = get_object_or_404(ProcurementCase.objects.select_related("notice"), pk=case_id)
    if case.stage != ProcurementCase.Stage.WON:
        return Response({"detail": "فقط پرونده برنده قابل تبدیل به پیش‌نویس قرارداد است."}, status=status.HTTP_409_CONFLICT)
    if request.data.get("confirmed") is not True:
        return Response({"detail": "تأیید صریح ایجاد پیش‌نویس قرارداد الزامی است."}, status=status.HTTP_400_BAD_REQUEST)

    proposed = _proposal(case)
    code = proposed["code"]
    existing = Contract.objects.filter(code=code).first()
    if existing:
        if existing.status != Contract.Status.DRAFT:
            return Response({"detail": "قرارداد متناظر از حالت پیش‌نویس خارج شده و قابل بازایجاد نیست."}, status=status.HTTP_409_CONFLICT)
        return Response({
            "created": False,
            "contract": ContractSerializer(existing).data,
            "requires_human_review": True,
            "financial_records_created": False,
        })

    title = str(request.data.get("title") or proposed["title"]).strip()[:300]
    employer = str(request.data.get("employer") or proposed["employer"]).strip()[:250]
    field = str(request.data.get("field") or "").strip()[:120]
    if not title or not employer:
        return Response({"detail": "عنوان و کارفرما برای ایجاد قرارداد الزامی هستند."}, status=status.HTTP_400_BAD_REQUEST)

    contract = Contract.objects.create(
        code=code,
        title=title,
        employer=employer,
        field=field,
        value_rials=request.data.get("value_rials") or proposed["value_rials"],
        due_date=request.data.get("due_date") or None,
        progress=0,
        status=Contract.Status.DRAFT,
        created_by=request.user,
    )
    AuditEvent.objects.create(
        actor=request.user.username,
        action="procurement.case.create_contract_draft",
        target_type="contract",
        target_id=str(contract.id),
        payload={
            "case_id": str(case.id),
            "notice_id": str(case.notice_id),
            "contract_code": contract.code,
            "contract_status": contract.status,
            "explicit_confirmation": True,
            "financial_records_created": False,
        },
    )
    return Response({
        "created": True,
        "contract": ContractSerializer(contract).data,
        "requires_human_review": True,
        "financial_records_created": False,
    }, status=status.HTTP_201_CREATED)
