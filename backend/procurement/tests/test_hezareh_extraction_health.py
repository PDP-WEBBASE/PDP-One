from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from procurement.connectors.hezareh import HezarehParser
from procurement.connectors.types import ParsedNotice
from procurement.http import FetchedPage
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementNotice, SourceNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


class HezarehParserHealthTests(SimpleTestCase):
    def setUp(self):
        self.parser = HezarehParser("https://www.hezarehinfo.net", "inquiry")

    def test_list_uses_source_page_report_and_extracts_insertion_date(self):
        html = """
        <html><body>
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>120001</td><td><a href="/inquiries/nid120001">استعلام خدمات طراحی</a></td>
          <td>استان تهران</td><td>1405/05/29</td><td>1405/06/02</td><td></td><td></td></tr>
        </tbody></table></div>
        <div class="pager-summary">صفحه 1 از 258503</div>
        <ul class="pagination">
          <li><a href="/inquiries/-%21/page-2">2</a></li>
          <li><a href="/inquiries/-%21/page-7">7</a></li>
        </ul>
        </body></html>
        """

        parsed = self.parser.parse_list(
            html,
            "https://www.hezarehinfo.net/inquiries/-%21/page-1",
        )

        self.assertEqual(len(parsed.notices), 1)
        notice = parsed.notices[0]
        self.assertEqual(notice.published_raw, "1405/05/29")
        self.assertEqual(notice.metadata["source_status"], "")
        self.assertFalse(notice.metadata["is_new_on_source"])
        self.assertEqual(parsed.reported_current_page, 1)
        self.assertEqual(parsed.reported_total_pages, 258503)
        self.assertEqual(parsed.diagnostics["reported_total_pages_source"], "source_report")
        self.assertEqual(parsed.diagnostics["visible_pagination_max"], 7)
        self.assertFalse(parsed.end_of_results)

    def test_new_marker_is_status_not_publication_date(self):
        html = """
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>120002</td><td><a href="/inquiries/nid120002">استعلام خدمات معماری</a></td>
          <td>استان تهران</td><td>جدید</td><td>1405/06/03</td><td></td><td></td></tr>
        </tbody></table></div>
        <div>صفحه 1 از 10</div>
        """

        parsed = self.parser.parse_list(
            html,
            "https://www.hezarehinfo.net/inquiries/-%21/page-1",
        )
        notice = parsed.notices[0]

        self.assertEqual(notice.published_raw, "")
        self.assertEqual(notice.metadata["source_status"], "جدید")
        self.assertTrue(notice.metadata["is_new_on_source"])

    def test_visible_pagination_window_does_not_claim_end_without_source_report(self):
        html = """
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr><td>120003</td><td><a href="/inquiries/nid120003">استعلام خدمات سازه</a></td>
          <td>استان تهران</td><td>1405/05/29</td><td>1405/06/03</td><td></td><td></td></tr>
        </tbody></table></div>
        <ul class="pagination"><li><a href="/inquiries/-%21/page-7">7</a></li></ul>
        """

        parsed = self.parser.parse_list(
            html,
            "https://www.hezarehinfo.net/inquiries/-%21/page-7",
        )

        self.assertEqual(parsed.reported_total_pages, 7)
        self.assertEqual(parsed.diagnostics["reported_total_pages_source"], "visible_links")
        self.assertIsNone(parsed.end_of_results)


class HezarehExtractionProcessTests(TestCase):
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
                source_url="https://www.hezarehinfo.net/inquiries/-%21/page-9",
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

    def _set_detail_enrichment_limit(self, connector: ProcurementConnector, limit: int):
        source = connector.source
        configuration = dict(source.configuration or {})
        configuration["hezareh_detail_enrichment_limit"] = limit
        source.configuration = configuration
        source.save(update_fields=["configuration", "updated_at"])

    def test_migrated_default_disables_automatic_detail_enrichment(self):
        connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        self.assertEqual(
            connector.source.configuration.get("hezareh_detail_enrichment_limit"),
            0,
        )

    def test_details_are_requested_only_after_list_known_boundary(self):
        connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        self._set_detail_enrichment_limit(connector, 1)
        self._seed_known(connector, "920002", "استعلام شناخته شده دو")
        self._seed_known(connector, "920003", "استعلام شناخته شده سه")

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            page_cap=5,
        )
        run.connectors.add(connector)

        events = []
        list_fetcher = Mock()
        pages = [
            ("920001", "استعلام جدید خدمات طراحی", 1),
            ("920002", "استعلام شناخته شده دو", 2),
            ("920003", "استعلام شناخته شده سه", 3),
        ]

        def fetch_list(page_number, url):
            events.append(f"list-{page_number}")
            record_id, title, page = pages[page_number - 1]
            return self._fetched(url, self._notice_html(record_id, title, page))

        list_fetcher.fetch_list.side_effect = fetch_list
        detail_fetcher = Mock()

        def fetch_detail(url):
            events.append("detail")
            return self._fetched(
                url,
                """
                <html><body>
                  <h1 class="entry-title">استعلام جدید خدمات طراحی</h1>
                  <div><b>برگزار کننده</b> شرکت نمونه</div>
                  <div><b>شرح آگهی</b> شرح کامل خدمات طراحی</div>
                  <div><b>تاریخ انتشار</b> 1405/05/29</div>
                  <div><b>مهلت ارسال</b> 1405/06/05</div>
                </body></html>
                """,
            )

        detail_fetcher.fetch_detail.side_effect = fetch_detail

        with patch(
            "procurement.tasks.fetcher_for",
            side_effect=[list_fetcher, detail_fetcher],
        ):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["detail_policy"], "deferred_after_list_boundary")
        self.assertEqual(summary["detail_candidates"], 1)
        self.assertEqual(summary["detail_attempted"], 1)
        self.assertEqual(summary["detail_enriched"], 1)
        self.assertEqual(events, ["list-1", "list-2", "list-3", "detail"])

        notice = ProcurementNotice.objects.get(source_links__source_notice__source_record_id="920001")
        self.assertEqual(notice.employer_name, "شرکت نمونه")
        self.assertEqual(notice.description, "شرح کامل خدمات طراحی")

    def test_detail_security_challenge_does_not_make_list_extraction_partial(self):
        connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        self._set_detail_enrichment_limit(connector, 1)
        self._seed_known(connector, "930002", "استعلام شناخته شده دو")
        self._seed_known(connector, "930003", "استعلام شناخته شده سه")

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            page_cap=5,
        )
        run.connectors.add(connector)

        list_fetcher = Mock()
        pages = [
            ("930001", "استعلام جدید معماری", 1),
            ("930002", "استعلام شناخته شده دو", 2),
            ("930003", "استعلام شناخته شده سه", 3),
        ]
        list_fetcher.fetch_list.side_effect = [
            self._fetched(
                f"https://www.hezarehinfo.net/inquiries/-%21/page-{page}",
                self._notice_html(record_id, title, page),
            )
            for record_id, title, page in pages
        ]
        detail_fetcher = Mock()
        detail_fetcher.fetch_detail.return_value = self._fetched(
            "https://www.hezarehinfo.net/inquiries/nid930001",
            "<html><title>کد امنیتی</title><body>جهت دسترسی به صفحه مورد نظر، کد امنیتی را وارد کنید</body></html>",
        )

        with patch(
            "procurement.tasks.fetcher_for",
            side_effect=[list_fetcher, detail_fetcher],
        ):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["hezareh_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS)
        self.assertEqual(summary["completeness"], "complete")
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["detail_access_limited"], 1)
        self.assertEqual(run.records_new, 1)
        source_notice = SourceNotice.objects.get(connector=connector, source_record_id="930001")
        self.assertEqual(source_notice.detail_status, SourceNotice.DetailStatus.NOT_REQUESTED)
