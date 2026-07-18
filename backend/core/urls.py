from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AnalysisReportViewSet, ContractViewSet, PaymentReceiptViewSet, ReceivableViewSet,
    financial_summary, management_summary, session_info, session_login, session_logout,
)

router = DefaultRouter()
router.register("contracts", ContractViewSet)
router.register("analysis-reports", AnalysisReportViewSet)
router.register("receivables", ReceivableViewSet)
router.register("payment-receipts", PaymentReceiptViewSet)
urlpatterns = [
    path("", include(router.urls)),
    path("management-summary/", management_summary),
    path("financial-summary/", financial_summary),
    path("auth/session/", session_info),
    path("auth/login/", session_login),
    path("auth/logout/", session_logout),
]
