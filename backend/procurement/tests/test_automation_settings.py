from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementConnector
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun
from procurement.tasks_automation import dispatch_due_extraction


class ProcurementAutomationSettingsTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="system-admin",
            password="test-pass",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.settings = ProcurementAutomationSettings.objects.get(key="default")

    def test_guarded_automation_is_enabled_once_with_pdp_draft_workflow(self):
        self.assertTrue(self.settings.enabled)
        self.assertEqual(self.settings.cadence, ProcurementAutomationSettings.Cadence.DAILY)
        self.assertEqual(str(self.settings.daily_time)[:5], "07:00")
        self.assertEqual(self.settings.manual_command, "PDP")
        self.assertEqual(self.settings.analysis_delay_minutes, 15)
        self.assertIsNotNone(self.settings.next_extraction_at)

    def test_daily_schedule_requires_time(self):
        response = self.client.patch(
            f"/api/v1/procurement/automation-settings/{self.settings.id}/",
            {"enabled": True, "cadence": "daily", "daily_time": None},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_hourly_schedule_sets_next_run_and_keeps_pdp_command(self):
        response = self.client.patch(
            f"/api/v1/procurement/automation-settings/{self.settings.id}/",
            {
                "enabled": True,
                "cadence": "hourly",
                "interval_minutes": 60,
                "analysis_delay_minutes": 60,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["manual_command"], "PDP")
        self.assertIsNotNone(response.data["next_extraction_at"])

    @patch("procurement.tasks_automation.run_extraction.delay")
    def test_dispatch_uses_only_enabled_connectors_and_requests_draft_analysis(self, mocked_delay):
        ProcurementConnector.objects.filter(key="parsnamad_inquiries").update(enabled=False)
        self.settings.enabled = True
        self.settings.cadence = ProcurementAutomationSettings.Cadence.HOURLY
        self.settings.interval_minutes = 60
        self.settings.next_extraction_at = timezone.now()
        self.settings.save()

        with self.captureOnCommitCallbacks(execute=True):
            result = dispatch_due_extraction()
        self.assertTrue(result["dispatched"])
        self.assertNotIn("parsnamad_inquiries", result["connector_keys"])
        run = ExtractionRun.objects.get(pk=result["run_id"])
        self.assertEqual(run.trigger, ExtractionRun.Trigger.SCHEDULED)
        self.assertTrue(run.analyze_after_success)
        self.assertFalse(run.connectors.filter(key="parsnamad_inquiries").exists())
        mocked_delay.assert_called_once_with(str(run.id))
