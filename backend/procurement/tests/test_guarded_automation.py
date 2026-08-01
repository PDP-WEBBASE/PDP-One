from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import AuditEvent
from procurement.analysis_run_service import initialize_run
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_analysis import AnalysisContextSnapshot, AnalysisRequest
from procurement.models_analysis_runs import ProcurementAnalysisRun
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun
from procurement.tasks_automation import (
    BOOTSTRAP_ACTION,
    bootstrap_guarded_automation,
    dispatch_due_analysis_requests,
    dispatch_due_extraction,
)


class GuardedAutomationTests(TestCase):
    def setUp(self):
        AuditEvent.objects.filter(action=BOOTSTRAP_ACTION).delete()
        ProcurementAutomationSettings.objects.filter(key="default").delete()
        ProcurementConnector.objects.update(enabled=False)
        ProcurementSource.objects.update(enabled=False)
        self.source = ProcurementSource.objects.create(
            key="automation-source",
            name="منبع زمان‌بندی",
            base_url="https://example.com",
            enabled=True,
        )
        self.connector = ProcurementConnector.objects.create(
            source=self.source,
            key="automation-tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            list_url_template="https://example.com/page-{page}",
            enabled=True,
            status=ProcurementConnector.Status.ACTIVE,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=81,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر زمان‌بندی‌شده",
            base_instructions="فقط پیش‌نویس ایجاد شود.",
            analysis_prompt="تحلیل کن.",
        )

    def test_bootstrap_is_one_time_and_respects_later_disable(self):
        first = bootstrap_guarded_automation()
        self.assertTrue(first["changed"])
        settings = ProcurementAutomationSettings.objects.get(key="default")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.cadence, ProcurementAutomationSettings.Cadence.HOURLY)
        self.assertEqual(settings.interval_minutes, 60)
        self.assertEqual(settings.analysis_delay_minutes, 0)
        settings.enabled = False
        settings.save(update_fields=["enabled", "updated_at"])

        second = bootstrap_guarded_automation()
        settings.refresh_from_db()
        self.assertFalse(second["changed"])
        self.assertFalse(settings.enabled)

    def test_due_extraction_is_incremental_and_requests_draft_analysis(self):
        bootstrap_guarded_automation()
        settings = ProcurementAutomationSettings.objects.get(key="default")
        settings.next_extraction_at = timezone.now() - timedelta(minutes=1)
        settings.save(update_fields=["next_extraction_at", "updated_at"])

        with self.captureOnCommitCallbacks(execute=False):
            result = dispatch_due_extraction.run()
        self.assertTrue(result["dispatched"])
        run = ExtractionRun.objects.get(pk=result["run_id"])
        self.assertEqual(run.trigger, ExtractionRun.Trigger.SCHEDULED)
        self.assertEqual(run.mode, ExtractionRun.Mode.INCREMENTAL)
        self.assertTrue(run.analyze_after_success)
        self.assertEqual(list(run.connectors.values_list("key", flat=True)), [self.connector.key])

    @patch("procurement.tasks_analysis_runs.initialize_analysis_run_task.delay")
    def test_scheduled_dispatch_creates_one_persistent_run_and_then_continues_it(self, mocked_delay):
        bootstrap_guarded_automation()

        first = dispatch_due_analysis_requests.run()
        second = dispatch_due_analysis_requests.run()

        self.assertEqual(first["created"], 1)
        self.assertTrue(first["persistent_run"])
        self.assertTrue(first["draft_only"])
        self.assertEqual(second["created"], 0)
        self.assertTrue(second["continued"])
        self.assertEqual(first["run_id"], second["run_id"])
        run = ProcurementAnalysisRun.objects.get(pk=first["run_id"])
        self.assertEqual(run.trigger, ProcurementAnalysisRun.Trigger.SCHEDULED)
        self.assertEqual(run.run_type, ProcurementAnalysisRun.RunType.INCREMENTAL)
        self.assertTrue(run.metadata["draft_only"])
        self.assertTrue(run.metadata["human_review_required"])
        mocked_delay.assert_called_once_with(str(run.id))

    @patch("procurement.tasks_analysis_runs.initialize_analysis_run_task.delay")
    def test_empty_persistent_run_finishes_as_no_changes(self, mocked_delay):
        bootstrap_guarded_automation()
        result = dispatch_due_analysis_requests.run()
        run = ProcurementAnalysisRun.objects.get(pk=result["run_id"])

        initialize_run(str(run.id), actor="test")
        run.refresh_from_db()

        self.assertEqual(run.status, ProcurementAnalysisRun.Status.NO_CHANGES)
        self.assertEqual(run.counters["total"], 0)
        self.assertEqual(run.analysis_request.status, AnalysisRequest.Status.NO_CHANGES)
        mocked_delay.assert_called_once_with(str(run.id))
