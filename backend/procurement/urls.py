from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InquiryViewSet, ProcurementConnectorViewSet, ProcurementNoticeViewSet, ProcurementSourceViewSet, TenderViewSet, procurement_dashboard
from .views_analysis import AnalysisBatchViewSet, AnalysisRequestViewSet, active_analysis_context, analysis_context_manifest, analysis_queue, notice_analysis_context
from .views_analysis_adaptive import claim_analysis_work_adaptive
from .views_analysis_engine import analysis_engine_work, finish_analysis_engine, start_analysis_engine
from .views_analysis_management import ManagedAnalysisContextAttachmentViewSet, ManagedAnalysisContextSnapshotViewSet
from .views_analysis_run_status_stats import analysis_run_status_with_statistics, current_analysis_run_with_statistics
from .views_analysis_runs import (
    analysis_dataset_status,
    analysis_import_status,
    analysis_run_history,
    analysis_run_queue_summary,
    analysis_run_status,
    cancel_analysis_run,
    current_analysis_run,
    download_analysis_dataset,
    import_analysis_results,
    pause_analysis_run,
    prepare_analysis_dataset,
    resume_analysis_run,
    start_full_pending_analysis,
    start_incremental_analysis,
)
from .views_analysis_statistics import analysis_statistics
from .views_automation import ProcurementAutomationSettingsViewSet
from .views_case_actions import ProcurementCaseViewSet
from .views_case_followup import case_follow_up, follow_up_summary, follow_up_users
from .views_compact_ui import bulk_dismiss_recommendations, compact_dashboard, compact_notice_feed
from .views_contract_draft import contract_draft_preview, create_contract_draft_from_case
from .views_direct import DirectOpportunityViewSet, OpportunityContactViewSet, OpportunityFollowUpViewSet, OpportunityResultViewSet
from .views_documents import ProcurementSubmissionDocumentViewSet
from .views_extraction import ExtractionRunViewSet
from .views_extraction_observability import latest_extraction_run
from .views_management_dashboard import unified_management_dashboard
from .views_internet_usage import internet_usage_dashboard
from .views_pagination_metrics import pagination_dashboard_metrics
from .views_recommended import AIRecommendedNoticeViewSet
from .views_review import AIReviewDraftViewSet, analysis_review_summary_view, review_analysis_draft, select_reviewed_analysis_draft
from .views_workflow_ui import workflow_page_metadata

router = DefaultRouter()
router.register("notices", ProcurementNoticeViewSet, basename="procurement-notice")
router.register("recommended-notices", AIRecommendedNoticeViewSet, basename="procurement-recommended-notice")
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
router.register("analysis-drafts", AIReviewDraftViewSet, basename="analysis-draft")
router.register("automation-settings", ProcurementAutomationSettingsViewSet, basename="automation-settings")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", procurement_dashboard, name="procurement-dashboard"),
    path("ui/notices/", compact_notice_feed, name="procurement-compact-notice-feed"),
    path("ui/dashboard/", compact_dashboard, name="procurement-compact-dashboard"),
    path("ui/workflow-page-metadata/", workflow_page_metadata, name="procurement-workflow-page-metadata"),
    path("ui/recommendations/dismiss-bulk/", bulk_dismiss_recommendations, name="procurement-bulk-dismiss-recommendations"),
    path("pagination-dashboard-metrics/", pagination_dashboard_metrics, name="procurement-pagination-dashboard-metrics"),
    path("management-dashboard/", unified_management_dashboard, name="procurement-management-dashboard"),
    path("internet-usage-dashboard/", internet_usage_dashboard, name="procurement-internet-usage-dashboard"),
    path("cases/follow-up/users/", follow_up_users, name="case-follow-up-users"),
    path("cases/follow-up/summary/", follow_up_summary, name="case-follow-up-summary"),
    path("cases/<uuid:case_id>/follow-up/", case_follow_up, name="case-follow-up"),
    path("cases/<uuid:case_id>/contract-preview/", contract_draft_preview, name="case-contract-preview"),
    path("cases/<uuid:case_id>/contract-draft/", create_contract_draft_from_case, name="case-contract-draft"),
    path("analysis/context/manifest/", analysis_context_manifest, name="analysis-context-manifest"),
    path("analysis/context/active/", active_analysis_context, name="analysis-context-active"),
    path("analysis/latest-extraction/", latest_extraction_run, name="analysis-latest-extraction"),
    path("analysis/queue/", analysis_queue, name="analysis-queue"),
    path("analysis/review-summary/", analysis_review_summary_view, name="analysis-review-summary"),
    path("analysis/notices/<uuid:notice_id>/context/", notice_analysis_context, name="notice-analysis-context"),
    path("analysis/engine/start/", start_analysis_engine, name="analysis-engine-start"),
    path("analysis/engine/requests/<uuid:request_id>/work/", analysis_engine_work, name="analysis-engine-work"),
    path("analysis/engine/requests/<uuid:request_id>/finish/", finish_analysis_engine, name="analysis-engine-finish"),
    path("analysis/engine/drafts/<uuid:draft_id>/review/", review_analysis_draft, name="analysis-engine-review"),
    path("analysis/engine/drafts/<uuid:draft_id>/select/", select_reviewed_analysis_draft, name="analysis-engine-select"),
    path("analysis/runs/queue-summary/", analysis_run_queue_summary, name="analysis-run-queue-summary"),
    path("analysis/runs/current/", current_analysis_run_with_statistics, name="analysis-run-current"),
    path("analysis/runs/history/", analysis_run_history, name="analysis-run-history"),
    path("analysis/runs/statistics/", analysis_statistics, name="analysis-run-statistics"),
    path("analysis/runs/full-pending/start/", start_full_pending_analysis, name="analysis-run-full-start"),
    path("analysis/runs/incremental/start/", start_incremental_analysis, name="analysis-run-incremental-start"),
    path("analysis/runs/<uuid:run_id>/", analysis_run_status_with_statistics, name="analysis-run-status"),
    path("analysis/runs/<uuid:run_id>/pause/", pause_analysis_run, name="analysis-run-pause"),
    path("analysis/runs/<uuid:run_id>/resume/", resume_analysis_run, name="analysis-run-resume"),
    path("analysis/runs/<uuid:run_id>/cancel/", cancel_analysis_run, name="analysis-run-cancel"),
    path("analysis/runs/<uuid:run_id>/claim/", claim_analysis_work_adaptive, name="analysis-run-claim"),
    path("analysis/runs/<uuid:run_id>/datasets/prepare/", prepare_analysis_dataset, name="analysis-dataset-prepare"),
    path("analysis/runs/<uuid:run_id>/results/import/", import_analysis_results, name="analysis-results-import"),
    path("analysis/datasets/<uuid:dataset_id>/", analysis_dataset_status, name="analysis-dataset-status"),
    path("analysis/datasets/<uuid:dataset_id>/download/<str:filename>/", download_analysis_dataset, name="analysis-dataset-download"),
    path("analysis/imports/<uuid:import_id>/", analysis_import_status, name="analysis-import-status"),
]
