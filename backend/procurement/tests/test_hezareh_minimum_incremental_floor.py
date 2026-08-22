from unittest.mock import Mock, patch

from django.test import TestCase

from procurement.connectors.types import ParsedNotice
from procurement.http import FetchedPage
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


class HezarehMinimumIncrementalFloorTests(TestCase):
    def _fetched(self, url: str, html: str) -> FetchedPage:
        content = html.encode("utf-8")
        return FetchedPage(url=url, status_code=200, content=content, text=html)

    def _notice_html(self, record_id: str, title: str, page: int) -> str:
        return f"""
        <html><body>
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>{record_id}</td><td><a href="/inquiries/nid{record_id}">{title}</a></td>
          <td>استان تهران</td><td>1405/05/29</td><td>1405/06/05</td><td></td><td></td></tr>
        </tbody></table></div>
        <div>صفحه {page} از 100</div>
        <ul class="pagination"><li><a href="/inquiries/-%21/page-{page + 1}">{page + 1}</a></li></ul>
        </body></html>
        """

    def _seed_known(self, connector: ProcurementConnector, record_id: str, title: str):
        ingest_parsed_notice(
            connector,
            ParsedNotice(
                source_record_id=record_id,
                source_url="https://www.hezarehinfo.net/inquiries",
                detail_url=f"https://www.hezarehinfo.net/inquiries/nid{record_id}",
                source_declared_type="inquiry",
                content_detected_type="inquiry",
                type_resolution_status="resolved",
                title=title,
                province="تهران",
                published_raw="1405/05/29",
                deadline_raw="1405/06/05",
            ),
        )

    def test_all_known_inquiries_still_fetch_page_three_before_known_boundary(self):
        connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        pages = [
            ("940001", "استعلام شناخته شده یک", 1),
            ("940002", "استعلام شناخته شده دو", 2),
            ("940003", "استعلام شناخته شده سه", 3),
        ]
        for record_id, title, _ in pages:
            self._seed_known(connector, record_id, title)

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=5,
        )
        run.connectors.add(connector)

        list_fetcher = Mock()

        def fetch_list(page_number, url):
            record_id, title, page = pages[page_number - 1]
            return self._fetched(url, self._notice_html(record_id, title, page))

        list_fetcher.fetch_list.side_effect = fetch_list

        with patch("procurement.tasks.fetcher_for", return_value=list_fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["last_successful_page"], 3)
        self.assertEqual(summary["known_boundary_pages"], 3)
        self.assertEqual(list_fetcher.fetch_list.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in list_fetcher.fetch_list.call_args_list],
            [1, 2, 3],
        )
