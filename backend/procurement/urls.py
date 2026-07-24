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
from .views_analysis import (
    AnalysisBatchViewSet,
    AnalysisRequestViewSet,
    NoticeAnalysisDraftViewSet,
    active_analysis_context,
    analysis_context_manifest,
    analysis_queue,
    latest_extraction_run,
    notice_analysis_context,
)
from .views_analysis_engine import (
    analysis_engine_work,
    finish_analysis_engine,
    review_analysis_draft,
    start_analysis_engine,
)
from .views_analysis_management import (
    ManagedAnalysisContextAttachmentViewSet,
    ManagedAnalysisContextSnapshotViewSet,
)
from .views_automation import ProcurementAutomationSettingsViewSet
from .views_direct import (
    DirectOpportunityViewSet,
    OpportunityContactViewSet,
    OpportunityFollowUpViewSet,
    OpportunityResultViewSet,
)
from .views_documents import ProcurementSubmissionDocumentViewSet
from .views_extraction import ExtractionRunViewSet

router = DefaultRouter()
router.register("notices", ProcurementNoticeViewSet, basename="procurement-notice")
router.register("tenders", TenderViewSet, basename="procurement-tender")
router.register("inquiries", InquiryViewSet, basename="procurement-inquiry")
router.register("cases", ProcurementCaseViewSet, basename="procurement-case")
router.register("sources", ProcurementSourceViewSet, basename="procurement-source")
router.register("connectors", ProcurementConnectorViewSet, basename="procurement-connector")
router.register("extraction-runs", ExtractionRunViewSet, basename="procurement-extraction-run")
router.register("direct-opportunities", DirectOpportunityViewSet, basename="direct-opportunity")
router.register("opportunity-contacts", OpportunityContactViewSet, basename="opportunity-contact")
router.register("opportunity-follow-ups", OpportunityFollowUpViewSet, basename="opportunity-follow-up")
router.register("opportunity-results", OpportunityResultViewSet, basename="opportunity-result")
router.register("submission-documents", ProcurementSubmissionDocumentViewSet, basename="submission-document")
router.register("analysis-contexts", ManagedAnalysisContextSnapshotViewSet, basename="analysis-context")
router.register("analysis-context-files", ManagedAnalysisContextAttachmentViewSet, basename="analysis-context-file")
router.register("analysis-requests", AnalysisRequestViewSet, basename="analysis-request")
router.register("analysis-batches", AnalysisBatchViewSet, basename="analysis-batch")
router.register("analysis-drafts", NoticeAnalysisDraftViewSet, basename="analysis-draft")
router.register("automation-settings", ProcurementAutomationSettingsViewSet, basename="automation-settings")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", procurement_dashboard, name="procurement-dashboard"),
    path("analysis/context/manifest/", analysis_context_manifest, name="analysis-context-manifest"),
    path("analysis/context/active/", active_analysis_context, name="analysis-context-active"),
    path("analysis/latest-extraction/", latest_extraction_run, name="analysis-latest-extraction"),
    path("analysis/queue/", analysis_queue, name="analysis-queue"),
    path("analysis/notices/<uuid:notice_id>/context/", notice_analysis_context, name="notice-analysis-context"),
    path("analysis/engine/start/", start_analysis_engine, name="analysis-engine-start"),
    path("analysis/engine/requests/<uuid:request_id>/work/", analysis_engine_work, name="analysis-engine-work"),
    path("analysis/engine/requests/<uuid:request_id>/finish/", finish_analysis_engine, name="analysis-engine-finish"),
    path("analysis/engine/drafts/<uuid:draft_id>/review/", review_analysis_draft, name="analysis-engine-review"),
]
