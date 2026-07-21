from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    InquiryViewSet,
    ProcurementCaseViewSet,
    ProcurementConnectorViewSet,
    ProcurementNoticeViewSet,
    ProcurementSourceViewSet,
    TenderViewSet,
    procurement_dashboard,
)
from .views_extraction import ExtractionRunViewSet

router = DefaultRouter()
router.register("notices", ProcurementNoticeViewSet, basename="procurement-notice")
router.register("tenders", TenderViewSet, basename="procurement-tender")
router.register("inquiries", InquiryViewSet, basename="procurement-inquiry")
router.register("cases", ProcurementCaseViewSet, basename="procurement-case")
router.register("sources", ProcurementSourceViewSet, basename="procurement-source")
router.register("connectors", ProcurementConnectorViewSet, basename="procurement-connector")
router.register("extraction-runs", ExtractionRunViewSet, basename="procurement-extraction-run")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", procurement_dashboard, name="procurement-dashboard"),
]
