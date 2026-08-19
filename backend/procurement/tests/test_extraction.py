from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from procurement.connectors.types import ParsedNotice
from procurement.http import FetchedPage
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementNotice
from procurement.models_extraction import ExtractionError, ExtractionRun
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

    @patch("procurement.views_extraction.run_extraction.delay")
    def test_manager_can_queue_approved_setad_connector(self, delay):
        self.client.force_authenticate(self.manager)
        setad = ProcurementConnector.objects.get(key="setad_tenders")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/procurement/extraction-runs/",
                {
                    "connector_ids": [str(setad.id)],
                    "include_details": False,
                    "page_cap": 2,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        run = ExtractionRun.objects.get()
        self.assertEqual(list(run.connectors.values_list("key", flat=True)), ["setad_tenders"])
        delay.assert_called_once_with(str(run.id))

    def test_explicitly_disabled_connector_is_rejected(self):
        self.client.force_authenticate(self.manager)
        setad = ProcurementConnector.objects.get(key="setad_tenders")
        setad.enabled = False
        setad.status = ProcurementConnector.Status.INACTIVE
        setad.save(update_fields=["enabled", "status", "updated_at"])
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
    def _fetched(self, url, html):
        content = html.encode("utf-8")
        return FetchedPage(
            url=url,
            status_code=200,
            content=content,
            text=html,
        )

    def test_unexpected_empty_page_is_retried_and_marks_run_partial(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        source = connector.source
        source.configuration = {
            **(source.configuration or {}),
            "content_retry_count": 2,
            "content_retry_delay_ms": 0,
        }
        source.save(update_fields=["configuration", "updated_at"])
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=2,
            summary={"controlled_live_test": True},
        )
        run.connectors.add(connector)
        first_html = """
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>10950416</td><td><a href="/tenders/nid10950416">مناقصه خدمات طراحی</a></td>
          <td>استان تهران</td><td>جدید</td><td>1405/05/05</td><td></td><td><i class="fa fa-hourglass-2"></i></td></tr>
        </tbody></table></div>
        <ul class="pagination"><li><a href="/tenders/-%21/page-10">10</a></li></ul>
        """
        empty_html = "<html><body><table></table></body></html>"
        fake_fetcher = Mock()
        fake_fetcher.fetch_list.side_effect = [
            self._fetched("https://www.hezarehinfo.net/tenders/-%21/page-1", first_html),
            self._fetched("https://www.hezarehinfo.net/tenders/-%21/page-2", empty_html),
            self._fetched("https://www.hezarehinfo.net/tenders/-%21/page-2", empty_html),
            self._fetched("https://www.hezarehinfo.net/tenders/-%21/page-2", empty_html),
        ]
        with patch("procurement.tasks.fetcher_for", return_value=fake_fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        connector.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.PARTIAL)
        self.assertEqual(run.pages_processed, 2)
        self.assertEqual(run.records_seen, 1)
        self.assertEqual(run.records_new, 1)
        self.assertEqual(ProcurementNotice.objects.count(), 1)
        self.assertEqual(result["status"], ExtractionRun.Status.PARTIAL)
        self.assertEqual(fake_fetcher.fetch_list.call_count, 4)
        self.assertTrue(run.summary["controlled_live_test"])
        summary = run.summary["connectors"]["hezareh_tenders"]
        self.assertEqual(summary["completeness"], "incomplete")
        self.assertEqual(summary["stop_reason"], "unexpected_empty_page")
        self.assertEqual(summary["reported_total_pages"], 10)
        self.assertEqual(summary["suspicious_pages"], [2])
        self.assertEqual(connector.status, ProcurementConnector.Status.ERROR)
        self.assertTrue(
            ExtractionError.objects.filter(
                run=run,
                connector=connector,
                category=ExtractionError.Category.VALIDATION,
                page_number=2,
            ).exists()
        )

    def test_identical_consecutive_pages_are_rejected_as_incomplete(self):
        connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        source = connector.source
        source.configuration = {
            **(source.configuration or {}),
            "content_retry_count": 0,
            "content_retry_delay_ms": 0,
        }
        source.save(update_fields=["configuration", "updated_at"])
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=2,
        )
        run.connectors.add(connector)
        html = """
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>20950416</td><td><a href="/inquiries/nid20950416">استعلام خدمات طراحی</a></td>
          <td>استان تهران</td><td>جدید</td><td>1405/05/05</td><td></td><td></td></tr>
        </tbody></table></div>
        <ul class="pagination"><li><a href="/inquiries/-%21/page-5">5</a></li></ul>
        """
        fake_fetcher = Mock()
        fake_fetcher.fetch_list.side_effect = [
            self._fetched("https://www.hezarehinfo.net/inquiries/-%21/page-1", html),
            self._fetched("https://www.hezarehinfo.net/inquiries/-%21/page-2", html),
        ]
        with patch("procurement.tasks.fetcher_for", return_value=fake_fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.PARTIAL)
        self.assertEqual(summary["stop_reason"], "duplicate_page_content")
        self.assertEqual(summary["suspicious_pages"], [2])
        self.assertEqual(run.records_seen, 1)

    def test_incremental_run_stops_after_two_semantically_known_pages(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        for record_id, old_page in (("900001", 8), ("900002", 9)):
            ingest_parsed_notice(
                connector,
                ParsedNotice(
                    source_record_id=record_id,
                    source_url=f"https://www.hezarehinfo.net/tenders/-%21/page-{old_page}",
                    detail_url=f"https://www.hezarehinfo.net/tenders/nid{record_id}",
                    source_declared_type="tender",
                    content_detected_type="tender",
                    type_resolution_status="resolved",
                    title=f"مناقصه شناخته شده {record_id}",
                    province="تهران",
                    deadline_raw="1405/06/01",
                    position=1,
                ),
            )

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=100,
        )
        run.connectors.add(connector)

        def page_html(record_id, total_page):
            return f"""
            <div class="table-1"><table class="table table-hover"><tbody>
              <tr><td>{record_id}</td><td><a href="/tenders/nid{record_id}">مناقصه شناخته شده {record_id}</a></td>
              <td>استان تهران</td><td></td><td>1405/06/01</td><td></td><td></td></tr>
            </tbody></table></div>
            <ul class="pagination"><li><a href="/tenders/-%21/page-{total_page}">{total_page}</a></li></ul>
            """

        fake_fetcher = Mock()
        fake_fetcher.fetch_list.side_effect = [
            self._fetched(
                "https://www.hezarehinfo.net/tenders/-%21/page-1",
                page_html("900001", 40),
            ),
            self._fetched(
                "https://www.hezarehinfo.net/tenders/-%21/page-2",
                page_html("900002", 40),
            ),
        ]
        with patch("procurement.tasks.fetcher_for", return_value=fake_fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_tenders"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(fake_fetcher.fetch_list.call_count, 2)
        self.assertEqual(run.records_updated, 0)
        self.assertEqual(run.records_duplicate, 2)
        self.assertEqual(summary["known_boundary_pages"], 2)
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["completeness"], "complete")

    def test_task_cancels_when_all_selected_connectors_are_disabled(self):
        connector = ProcurementConnector.objects.get(key="setad_tenders")
        connector.enabled = False
        connector.status = ProcurementConnector.Status.INACTIVE
        connector.save(update_fields=["enabled", "status", "updated_at"])
        run = ExtractionRun.objects.create(status=ExtractionRun.Status.QUEUED)
        run.connectors.add(connector)

        result = run_extraction(str(run.id))

        run.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.CANCELLED)
        self.assertEqual(result["summary"]["skipped_disabled_connectors"], ["setad_tenders"])
