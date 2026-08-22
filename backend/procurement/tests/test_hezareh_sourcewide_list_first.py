from unittest.mock import Mock, patch

from django.test import TestCase

from procurement.http import FetchedPage
from procurement.models import ProcurementConnector
from procurement.models_extraction import ExtractionError, ExtractionPage, ExtractionRun
from procurement.tasks import run_extraction


class HezarehSourceWideListFirstTests(TestCase):
    def _summary(self):
        return {
            "status": "succeeded",
            "pages": 1,
            "seen": 1,
            "new": 0,
            "updated": 0,
            "duplicate": 1,
            "failed": 0,
            "warnings": 0,
        }

    def test_all_connector_lists_finish_before_hezareh_detail_jobs(self):
        inquiry = ProcurementConnector.objects.get(key="hezareh_inquiries")
        tender = ProcurementConnector.objects.get(key="hezareh_tenders")
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            page_cap=2,
        )
        run.connectors.add(inquiry, tender)

        events = []

        def execute(run_obj, connector, *, hezareh_detail_jobs=None):
            events.append(f"list:{connector.key}")
            summary = self._summary()
            hezareh_detail_jobs.append(
                {
                    "connector": connector,
                    "parser": Mock(),
                    "allowed_host": "www.hezarehinfo.net",
                    "candidates": [(Mock(), 1)],
                    "summary": summary,
                }
            )
            return summary

        def enrich(**kwargs):
            events.append(f"detail:{kwargs['connector'].key}")

        with patch("procurement.tasks._execute_connector", side_effect=execute), patch(
            "procurement.tasks._enrich_hezareh_details_after_list", side_effect=enrich
        ):
            run_extraction(str(run.id))

        first_detail = next(index for index, event in enumerate(events) if event.startswith("detail:"))
        self.assertTrue(all(event.startswith("list:") for event in events[:first_detail]))
        self.assertEqual(sum(event.startswith("list:") for event in events), 2)
        self.assertEqual(sum(event.startswith("detail:") for event in events), 2)

    def test_list_security_challenge_is_classified_explicitly(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        source = connector.source
        source.configuration = {**(source.configuration or {}), "content_retry_count": 0}
        source.save(update_fields=["configuration", "updated_at"])

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=1,
        )
        run.connectors.add(connector)

        html = (
            "<html><title>کد امنیتی</title><body>"
            "جهت دسترسی به صفحه مورد نظر، کد امنیتی را وارد کنید"
            "</body></html>"
        )
        fetched = FetchedPage(
            url="https://www.hezarehinfo.net/tenders",
            status_code=200,
            content=html.encode("utf-8"),
            text=html,
        )
        fetcher = Mock()
        fetcher.fetch_list.return_value = fetched

        with patch("procurement.tasks.fetcher_for", return_value=fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_tenders"]
        page = ExtractionPage.objects.get(run=run, connector=connector, page_number=1)
        error = ExtractionError.objects.filter(run=run, connector=connector).latest("created_at")

        self.assertEqual(result["status"], ExtractionRun.Status.PARTIAL)
        self.assertEqual(summary["stop_reason"], "security_challenge")
        self.assertEqual(page.error_code, "security_challenge")
        self.assertEqual(error.category, ExtractionError.Category.SECURITY_CHALLENGE)
