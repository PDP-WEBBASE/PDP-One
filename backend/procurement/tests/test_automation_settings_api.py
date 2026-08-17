from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import AuditEvent
from procurement.models_automation import ProcurementAutomationSettings


class ProcurementAutomationSettingsApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(username="schedule-viewer", password="test-pass-123")
        self.admin = User.objects.create_user(
            username="schedule-admin",
            password="test-pass-123",
            is_staff=True,
        )
        self.client = APIClient()
        ProcurementAutomationSettings.objects.all().delete()

    def test_default_get_is_read_only_when_record_is_missing(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.get("/api/v1/procurement/automation-settings/default/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ProcurementAutomationSettings.objects.count(), 0)

    def test_admin_patch_creates_default_record_and_saves_daily_eleven(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            "/api/v1/procurement/automation-settings/default/",
            {
                "enabled": True,
                "cadence": "daily",
                "interval_minutes": 60,
                "daily_time": "11:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProcurementAutomationSettings.objects.count(), 1)
        settings = ProcurementAutomationSettings.objects.get(key="default")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.cadence, ProcurementAutomationSettings.Cadence.DAILY)
        self.assertEqual(settings.daily_time.strftime("%H:%M"), "11:00")
        self.assertEqual(settings.timezone_name, "Asia/Tehran")
        self.assertIsNotNone(settings.next_extraction_at)
        self.assertEqual(settings.updated_by, self.admin)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="procurement.automation_settings.update",
                target_id=str(settings.id),
            ).exists()
        )

    def test_second_patch_updates_same_record_to_hourly(self):
        settings = ProcurementAutomationSettings.objects.create(
            key="default",
            enabled=False,
            cadence=ProcurementAutomationSettings.Cadence.DAILY,
            daily_time="11:00",
            interval_minutes=60,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            "/api/v1/procurement/automation-settings/default/",
            {
                "enabled": True,
                "cadence": "hourly",
                "interval_minutes": 120,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProcurementAutomationSettings.objects.count(), 1)
        settings.refresh_from_db()
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.cadence, ProcurementAutomationSettings.Cadence.HOURLY)
        self.assertEqual(settings.interval_minutes, 120)

    def test_non_admin_cannot_change_default_schedule(self):
        ProcurementAutomationSettings.objects.create(key="default")
        self.client.force_authenticate(self.viewer)

        response = self.client.patch(
            "/api/v1/procurement/automation-settings/default/",
            {"enabled": True, "cadence": "hourly", "interval_minutes": 60},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_enabled_daily_schedule_requires_time(self):
        ProcurementAutomationSettings.objects.create(key="default", daily_time=None)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            "/api/v1/procurement/automation-settings/default/",
            {"enabled": True, "cadence": "daily", "daily_time": None},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("daily_time", response.data)
