from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import AuditEvent
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_analysis import AnalysisContextSnapshot, AnalysisRequest
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
        self.assertEqual(settings.analysis_delay_minutes, 15)
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

    def test_analysis_request_is_created_once_only_for_changed_records(self):
        bootstrap_guarded_automation()
        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            status=ExtractionRun.Status.SUCCEEDED,
            analyze_after_success=True,
            records_new=2,
            records_updated=1,
        )
        run.connectors.add(self.connector)

        first = dispatch_due_analysis_requests.run()
        second = dispatch_due_analysis_requests.run()
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        request_record = AnalysisRequest.objects.get(extraction_run=run)
        self.assertEqual(request_record.trigger, AnalysisRequest.Trigger.SCHEDULED)
        self.assertEqual(request_record.status, AnalysisRequest.Status.PENDING)
        self.assertTrue(request_record.metadata["draft_only"])
        self.assertTrue(request_record.metadata["human_review_required"])

    def test_no_changes_are_closed_without_analysis_work(self):
        bootstrap_guarded_automation()
        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            status=ExtractionRun.Status.SUCCEEDED,
            analyze_after_success=True,
            records_new=0,
            records_updated=0,
        )
        run.connectors.add(self.connector)
        result = dispatch_due_analysis_requests.run()
        self.assertEqual(result["created"], 0)
        request_record = AnalysisRequest.objects.get(extraction_run=run)
        self.assertEqual(request_record.status, AnalysisRequest.Status.NO_CHANGES)
