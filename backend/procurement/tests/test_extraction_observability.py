from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from procurement.models import ProcurementConnector
from procurement.models_extraction import ExtractionPage, ExtractionRun
from procurement.views_extraction_observability import latest_extraction_run


class ExtractionObservabilityTests(TestCase):
    def setUp(self):
        ExtractionRun.objects.all().delete()
        self.connector = ProcurementConnector.objects.get(key="setad_inquiries")
        self.user = get_user_model().objects.create_user(
            username="extraction-observer",
            password="test-only-password",
        )
        self.factory = APIRequestFactory()
        self.now = timezone.now().replace(microsecond=0)

    def _get_latest(self):
        request = self.factory.get("/api/v1/procurement/analysis/latest-extraction/")
        force_authenticate(request, user=self.user)
        with patch("procurement.views_extraction_observability.timezone.now", return_value=self.now):
            return latest_extraction_run(request)

    def test_active_running_extraction_is_visible_even_without_completed_run(self):
        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.RUNNING,
            started_at=self.now - timedelta(hours=1),
        )
        run.connectors.add(self.connector)
        ExtractionRun.objects.filter(pk=run.pk).update(
            created_at=self.now - timedelta(hours=1, minutes=1),
            updated_at=self.now - timedelta(minutes=20),
        )
        page = ExtractionPage.objects.create(
            run=run,
            connector=self.connector,
            page_number=3,
            url="https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-test-p=3",
            http_status=200,
            parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
            captured_at=self.now - timedelta(minutes=10),
        )

        response = self._get_latest()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["active_run_count"], 1)
        active = response.data["active_runs"][0]
        self.assertEqual(active["id"], str(run.id))
        self.assertEqual(active["status"], ExtractionRun.Status.RUNNING)
        self.assertEqual(active["connector_keys"], ["setad_inquiries"])
        self.assertEqual(active["pages_recorded"], 1)
        self.assertEqual(active["items_recorded"], 0)
        self.assertEqual(active["errors_recorded"], 0)
        self.assertEqual(active["idle_seconds"], 600)
        self.assertEqual(active["latest_page"]["page_number"], page.page_number)
        self.assertEqual(active["latest_page"]["connector_key"], "setad_inquiries")
        self.assertEqual(active["latest_page"]["parse_status"], ExtractionPage.ParseStatus.SUCCEEDED)

    def test_completed_shape_is_preserved_while_active_blocker_is_added(self):
        completed = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.SUCCEEDED,
            finished_at=self.now - timedelta(minutes=30),
            records_new=4,
            records_updated=2,
            records_failed=0,
        )
        completed.connectors.add(self.connector)
        queued = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.QUEUED,
        )
        queued.connectors.add(self.connector)

        response = self._get_latest()

        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["id"], str(completed.id))
        self.assertEqual(response.data["records_new"], 4)
        self.assertEqual(response.data["records_updated"], 2)
        self.assertEqual(response.data["records_failed"], 0)
        self.assertEqual(response.data["connector_keys"], ["setad_inquiries"])
        self.assertEqual(response.data["active_run_count"], 1)
        self.assertEqual(response.data["active_runs"][0]["id"], str(queued.id))
        self.assertEqual(response.data["active_runs"][0]["status"], ExtractionRun.Status.QUEUED)
