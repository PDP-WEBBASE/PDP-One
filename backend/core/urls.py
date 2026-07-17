from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import AnalysisReportViewSet, ContractViewSet, management_summary

router = DefaultRouter()
router.register("contracts", ContractViewSet)
router.register("analysis-reports", AnalysisReportViewSet)
urlpatterns = [path("", include(router.urls)), path("management-summary/", management_summary)]

