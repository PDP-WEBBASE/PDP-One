from django.db.models import Count, Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import AnalysisReport, AuditEvent, Contract
from .serializers import AnalysisReportSerializer, ContractSerializer

class ContractViewSet(ModelViewSet):
    queryset = Contract.objects.all().order_by("-created_at")
    serializer_class = ContractSerializer
    search_fields = ["code", "title", "employer", "field"]
    filterset_fields = ["status", "field"]
    def perform_create(self, serializer):
        contract = serializer.save(created_by=self.request.user, status=Contract.Status.DRAFT)
        AuditEvent.objects.create(actor=self.request.user.username, action="contract.create_draft", target_type="contract", target_id=str(contract.id), payload={"code": contract.code})

class AnalysisReportViewSet(ModelViewSet):
    queryset = AnalysisReport.objects.all().order_by("-created_at")
    serializer_class = AnalysisReportSerializer
    search_fields = ["title", "summary"]
    def perform_create(self, serializer):
        report = serializer.save(requested_by=self.request.user, review_status=AnalysisReport.ReviewStatus.AI_DRAFT)
        AuditEvent.objects.create(actor=self.request.user.username, action="analysis.create_draft", target_type="analysis_report", target_id=str(report.id), payload={"source_count": len(report.source_record_ids)})

@api_view(["GET"])
def management_summary(request):
    contracts = Contract.objects.all()
    return Response({"contract_count": contracts.count(), "active_count": contracts.filter(status=Contract.Status.ACTIVE).count(), "critical_count": contracts.filter(status=Contract.Status.CRITICAL).count(), "open_value_rials": contracts.exclude(status=Contract.Status.CLOSED).aggregate(total=Sum("value_rials"))["total"] or 0, "by_status": list(contracts.values("status").annotate(count=Count("id")))})

