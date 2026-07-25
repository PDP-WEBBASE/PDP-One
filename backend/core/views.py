import os

from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Sum
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import mixins
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.viewsets import GenericViewSet
from .models import AnalysisReport, AuditEvent, Contract, PaymentReceipt, Receivable
from .serializers import AnalysisReportSerializer, ContractSerializer, PaymentReceiptSerializer, ReceivableSerializer


class DraftCreateReadViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    """Create and read drafts; approval and destructive changes stay in the admin workflow."""


class ContractViewSet(DraftCreateReadViewSet):
    queryset = Contract.objects.all().order_by("-created_at")
    serializer_class = ContractSerializer
    search_fields = ["code", "title", "employer", "field"]
    filterset_fields = ["status", "field"]
    ordering_fields = ["created_at", "due_date", "value_rials", "progress"]

    def perform_create(self, serializer):
        contract = serializer.save(created_by=self.request.user, status=Contract.Status.DRAFT)
        AuditEvent.objects.create(actor=self.request.user.username, action="contract.create_draft", target_type="contract", target_id=str(contract.id), payload={"code": contract.code})


class AnalysisReportViewSet(DraftCreateReadViewSet):
    queryset = AnalysisReport.objects.all().order_by("-created_at")
    serializer_class = AnalysisReportSerializer
    search_fields = ["title", "summary"]

    def perform_create(self, serializer):
        report = serializer.save(requested_by=self.request.user, review_status=AnalysisReport.ReviewStatus.AI_DRAFT)
        AuditEvent.objects.create(actor=self.request.user.username, action="analysis.create_draft", target_type="analysis_report", target_id=str(report.id), payload={"source_count": len(report.source_record_ids)})


def _release_connector_acceptance_status():
    from procurement.models_extraction import ExtractionRun
    from procurement.tasks_acceptance import AUTO_ACCEPTANCE_CONNECTORS, AUTO_ACCEPTANCE_SUITE_ID

    runs = list(
        ExtractionRun.objects.filter(summary__acceptance__suite_id=AUTO_ACCEPTANCE_SUITE_ID)
        .prefetch_related("connectors__source", "errors", "items__source_notice")
        .order_by("created_at")
    )
    terminal = {
        ExtractionRun.Status.SUCCEEDED,
        ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
        ExtractionRun.Status.PARTIAL,
        ExtractionRun.Status.FAILED,
        ExtractionRun.Status.CANCELLED,
    }
    summaries = []
    for run in runs:
        connector = run.connectors.select_related("source").first()
        sample_item = run.items.select_related("source_notice").order_by("page_number", "position").first()
        source_notice = sample_item.source_notice if sample_item else None
        normalized = None
        if source_notice is not None:
            try:
                notice = source_notice.notice_link.procurement_notice
                normalized = {
                    "id": str(notice.id),
                    "title": notice.title,
                    "employer": notice.employer_name,
                    "notice_type": notice.resolved_notice_type,
                }
            except Exception:
                normalized = None
        connector_key = connector.key if connector else ""
        summaries.append(
            {
                "run_id": str(run.id),
                "connector_key": connector_key,
                "source": connector.source.name if connector else "",
                "notice_type": connector.notice_type if connector else "",
                "status": run.status,
                "terminal": run.status in terminal,
                "pages": run.pages_processed,
                "records_seen": run.records_seen,
                "new": run.records_new,
                "updated": run.records_updated,
                "duplicates": run.records_duplicate,
                "failed": run.records_failed,
                "errors": run.errors.count(),
                "source_url_sample": source_notice.source_url if source_notice else "",
                "raw_data_present": bool(source_notice and source_notice.raw_payload),
                "raw_data_keys": sorted((source_notice.raw_payload or {}).keys())[:20] if source_notice else [],
                "standardized_data_present": normalized is not None,
                "standardized_sample": normalized,
                "connector_summary": (run.summary or {}).get("connectors", {}).get(connector_key, {}),
            }
        )

    if not runs:
        overall = "not_started"
    elif any(run.status not in terminal for run in runs):
        overall = "running"
    elif len(runs) != len(AUTO_ACCEPTANCE_CONNECTORS):
        overall = "incomplete"
    elif all(run.status in {ExtractionRun.Status.SUCCEEDED, ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS} for run in runs):
        overall = "completed"
    else:
        overall = "needs_attention"

    return {
        "suite_id": AUTO_ACCEPTANCE_SUITE_ID,
        "overall_status": overall,
        "expected_connectors": list(AUTO_ACCEPTANCE_CONNECTORS),
        "run_count": len(runs),
        "connectors": summaries,
    }


@api_view(["GET"])
def system_status(request):
    """Small authenticated diagnostic used by the MCP connection check."""
    return Response({
        "service": "PDP One",
        "database": "connected",
        "trial_mode": os.getenv("PDP_TRIAL_MODE", "false").lower() in {"1", "true", "yes"},
        "contracts": Contract.objects.count(),
        "receivables": Receivable.objects.count(),
        "analysis_drafts": AnalysisReport.objects.count(),
        "connector_acceptance": _release_connector_acceptance_status(),
    })


class ReceivableViewSet(DraftCreateReadViewSet):
    queryset = Receivable.objects.all().order_by("due_date", "-created_at")
    serializer_class = ReceivableSerializer
    search_fields = ["reference_code", "contract_code", "contract_title", "employer", "statement_title"]
    filterset_fields = ["status", "contract_code", "due_date"]
    ordering_fields = ["due_date", "amount_rials", "created_at"]

    def perform_create(self, serializer):
        record = serializer.save(created_by=self.request.user, status=Receivable.Status.DRAFT)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="receivable.create_draft",
            target_type="receivable",
            target_id=str(record.id),
            payload={"reference_code": record.reference_code, "contract_code": record.contract_code},
        )


class PaymentReceiptViewSet(DraftCreateReadViewSet):
    queryset = PaymentReceipt.objects.select_related("receivable").all()
    serializer_class = PaymentReceiptSerializer
    search_fields = ["tracking_code", "note", "receivable__reference_code", "receivable__contract_code"]
    filterset_fields = ["status", "receivable"]
    ordering_fields = ["received_date", "amount_rials", "created_at"]

    def perform_create(self, serializer):
        receipt = serializer.save(created_by=self.request.user, status=PaymentReceipt.Status.DRAFT)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="payment_receipt.create_draft",
            target_type="payment_receipt",
            target_id=str(receipt.id),
            payload={"receivable_id": str(receipt.receivable_id), "amount_rials": str(receipt.amount_rials)},
        )


@api_view(["GET"])
def management_summary(request):
    contracts = Contract.objects.all()
    return Response({"contract_count": contracts.count(), "active_count": contracts.filter(status=Contract.Status.ACTIVE).count(), "critical_count": contracts.filter(status=Contract.Status.CRITICAL).count(), "open_value_rials": contracts.exclude(status=Contract.Status.CLOSED).aggregate(total=Sum("value_rials"))["total"] or 0, "by_status": list(contracts.values("status").annotate(count=Count("id")))})


@api_view(["GET"])
def financial_summary(request):
    receivables = Receivable.objects.all()
    open_records = receivables.exclude(status__in=[Receivable.Status.PAID, Receivable.Status.CANCELLED])
    total_amount = open_records.aggregate(total=Sum("amount_rials"))["total"] or 0
    total_received = open_records.aggregate(total=Sum("received_rials"))["total"] or 0
    return Response({
        "open_amount_rials": total_amount - total_received,
        "overdue_amount_rials": receivables.filter(status=Receivable.Status.OVERDUE).aggregate(total=Sum("amount_rials"))["total"] or 0,
        "collected_amount_rials": receivables.aggregate(total=Sum("received_rials"))["total"] or 0,
        "due_soon_count": receivables.filter(status=Receivable.Status.DUE_SOON).count(),
        "open_count": open_records.count(),
        "by_status": list(receivables.values("status").annotate(count=Count("id"))),
    })


@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def session_info(request):
    return Response({
        "authenticated": request.user.is_authenticated,
        "username": request.user.username if request.user.is_authenticated else None,
        "csrf_token": get_token(request),
    })


@csrf_protect
@api_view(["POST"])
@permission_classes([AllowAny])
def session_login(request):
    user = authenticate(request, username=request.data.get("username", ""), password=request.data.get("password", ""))
    if user is None or not user.is_active:
        return Response({"detail": "نام کاربری یا رمز عبور صحیح نیست."}, status=HTTP_400_BAD_REQUEST)
    login(request, user)
    AuditEvent.objects.create(actor=user.username, action="session.login", target_type="user", target_id=str(user.pk))
    return Response({"authenticated": True, "username": user.username})


@csrf_protect
@api_view(["POST"])
def session_logout(request):
    username = request.user.username
    logout(request)
    AuditEvent.objects.create(actor=username, action="session.logout", target_type="user")
    return Response({"authenticated": False})
