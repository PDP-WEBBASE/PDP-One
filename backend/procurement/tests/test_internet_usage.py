from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_extraction import ExtractionPage, ExtractionRun


class InternetUsageDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="manager", password="secret")
        self.source = ProcurementSource.objects.create(key="test-source", name="Test", base_url="https://example.com")
        self.connector = ProcurementConnector.objects.create(
            source=self.source,
            key="test-tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            list_url_template="https://example.com/{page}",
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/v1/procurement/internet-usage-dashboard/")
        self.assertIn(response.status_code, {401, 403})

    def test_reports_existing_real_response_bytes_without_hot_path_instrumentation(self):
        run = ExtractionRun.objects.create(status=ExtractionRun.Status.SUCCEEDED, started_at=timezone.now())
        run.connectors.add(self.connector)
        ExtractionPage.objects.create(
            run=run,
            connector=self.connector,
            page_number=1,
            url="https://example.com/1",
            response_bytes=1536,
            captured_at=timezone.now(),
            parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
        )
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/v1/procurement/internet-usage-dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["uses_real_data_only"])
        self.assertEqual(response.data["mode"], "passive_read_only")
        activities = {item["key"]: item for item in response.data["activities"]}
        self.assertEqual(activities["extraction"]["periods"]["24h"]["download_bytes"], 1536)
        self.assertEqual(activities["extraction"]["periods"]["7d"]["total_bytes"], 1536)
        self.assertEqual(activities["extraction"]["periods"]["all"]["total_bytes"], 1536)
        self.assertEqual(response.data["measured_totals"]["all"], 1536)
        self.assertEqual(response.data["performance"]["hot_path_writes_added"], 0)
        self.assertFalse(response.data["performance"]["packet_capture"])
        self.assertFalse(activities["ci_images"]["measured"])
        self.assertIsNone(activities["ci_images"]["periods"]["24h"]["total_bytes"])
        self.assertNotIn("recent_runs", response.data)
