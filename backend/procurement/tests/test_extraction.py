from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from procurement.http import FetchedPage
from procurement.models import ProcurementConnector, ProcurementNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


class ExtractionRunApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="expert-run", password="test-pass-123")
        self.manager = User.objects.create_user(
            username="manager-run",
            password="test-pass-123",
            is_staff=True,
        )
        self.client = APIClient()
        self.connector = ProcurementConnector.objects.get(key="hezareh_tenders")

    def test_regular_user_cannot_start_extraction(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/procurement/extraction-runs/",
            {"connector_ids": [str(self.connector.id)], "include_details": False},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @patch("procurement.views_extraction.run_extraction.delay")
    def test_manager_can_queue_selected_active_connectors(self, delay):
        self.client.force_authenticate(self.manager)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/procurement/extraction-runs/",
                {
                    "connector_ids": [str(self.connector.id)],
                    "include_details": False,
                    "page_cap": 2,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        run = ExtractionRun.objects.get()
        self.assertEqual(run.status, ExtractionRun.Status.QUEUED)
        self.assertEqual(list(run.connectors.values_list("key", flat=True)), ["hezareh_tenders"])
        delay.assert_called_once_with(str(run.id))

    def test_disabled_pending_connector_is_rejected(self):
        self.client.force_authenticate(self.manager)
        setad = ProcurementConnector.objects.get(key="setad_tenders")
        response = self.client.post(
            "/api/v1/procurement/extraction-runs/",
            {"connector_ids": [str(setad.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("connector_ids", response.data)

    def test_second_run_for_same_connector_is_rejected_while_first_is_queued(self):
        existing = ExtractionRun.objects.create(status=ExtractionRun.Status.QUEUED)
        existing.connectors.add(self.connector)
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/v1/procurement/extraction-runs/",
            {"connector_ids": [str(self.connector.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("connector_ids", response.data)


class ExtractionTaskTests(TestCase):
    def test_task_processes_list_pages_and_stops_on_empty_page(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=2,
        )
        run.connectors.add(connector)
        first_html = b"""
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>10950416</td><td><a href="/tenders/nid10950416">مناقصه خدمات طراحی</a></td>
          <td>استان تهران</td><td>جدید</td><td>1405/05/05</td><td></td><td><i class="fa fa-hourglass-2"></i></td></tr>
        </tbody></table></div>
        """
        empty_html = b"<html><body><table></table></body></html>"
        responses = [
            FetchedPage(
                url="https://www.hezarehinfo.net/tenders/-%21/page-1",
                status_code=200,
                content=first_html,
                text=first_html.decode("utf-8"),
            ),
            FetchedPage(
                url="https://www.hezarehinfo.net/tenders/-%21/page-2",
                status_code=200,
                content=empty_html,
                text=empty_html.decode("utf-8"),
            ),
        ]
        with patch("procurement.tasks.fetch_public_html", side_effect=responses):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS)
        self.assertEqual(run.pages_processed, 2)
        self.assertEqual(run.records_seen, 1)
        self.assertEqual(run.records_new, 1)
        self.assertEqual(ProcurementNotice.objects.count(), 1)
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS)

    def test_task_cancels_when_all_selected_connectors_are_disabled(self):
        connector = ProcurementConnector.objects.get(key="setad_tenders")
        run = ExtractionRun.objects.create(status=ExtractionRun.Status.QUEUED)
        run.connectors.add(connector)

        result = run_extraction(str(run.id))

        run.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.CANCELLED)
        self.assertEqual(result["summary"]["skipped_disabled_connectors"], ["setad_tenders"])
