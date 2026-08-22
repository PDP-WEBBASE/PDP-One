from unittest.mock import Mock, patch

from django.test import TestCase

from procurement.connectors.types import ParsedNotice
from procurement.http import FetchedPage
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, SourceNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


class ParsNamadInquiryProcessTests(TestCase):
    def _fetched(self, url: str, html: str) -> FetchedPage:
        content = html.encode("utf-8")
        return FetchedPage(url=url, status_code=200, content=content, text=html)

    def _notice_html(
        self,
        record_id: str,
        title: str,
        page: int,
        *,
        province: str = "تهران",
        published_raw: str = "1405/05/29",
    ) -> str:
        return f"""
        <html><body>
          <table><tbody id="search_result_list">
            <tr class="text-center">
              <th>1</th><td></td>
              <td><a href="/inquiry/{record_id}/sample">{title}</a></td>
              <td><a href="/inquiry/{record_id}/sample">{record_id}</a></td>
              <td>{published_raw}</td>
              <td><img src="/pnd/img/search-icons/new-large.png"></td>
              <td>{province}</td>
            </tr>
          </tbody></table>
          <ul class="pagination">
            <li><a href="/inquiries/page/{page + 1}">{page + 1}</a></li>
          </ul>
        </body></html>
        """

    def _seed_known(
        self,
        connector: ProcurementConnector,
        record_id: str,
        title: str,
        *,
        province: str = "تهران",
        published_raw: str = "1405/05/29",
        detail: dict | None = None,
    ) -> SourceNotice:
        source_notice, _, _ = ingest_parsed_notice(
            connector,
            ParsedNotice(
                source_record_id=record_id,
                source_url="https://www.parsnamaddata.com/inquiries/page/9",
                detail_url=f"https://www.parsnamaddata.com/inquiry/{record_id}/sample",
                source_declared_type="inquiry",
                content_detected_type="inquiry",
                type_resolution_status="resolved",
                title=title,
                province=province,
                published_raw=published_raw,
            ),
            detail=detail,
        )
        return source_notice

    def test_all_known_incremental_pages_issue_zero_detail_requests(self):
        connector = ProcurementConnector.objects.get(key="parsnamad_inquiries")
        self._seed_known(
            connector,
            "960001",
            "استعلام شناخته شده یک",
            detail={
                "detail_status": "enriched",
                "description": "شرح غنی یک",
                "deadline_raw": "1405/06/10",
            },
        )
        self._seed_known(
            connector,
            "960002",
            "استعلام شناخته شده دو",
            detail={
                "detail_status": "enriched",
                "description": "شرح غنی دو",
                "deadline_raw": "1405/06/11",
            },
        )

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            page_cap=5,
        )
        run.connectors.add(connector)

        list_fetcher = Mock()
        list_fetcher.fetch_list.side_effect = [
            self._fetched(
                "https://www.parsnamaddata.com/inquiries/page/1",
                self._notice_html("960001", "استعلام شناخته شده یک", 1),
            ),
            self._fetched(
                "https://www.parsnamaddata.com/inquiries/page/2",
                self._notice_html("960002", "استعلام شناخته شده دو", 2),
            ),
        ]
        list_fetcher.fetch_detail.side_effect = AssertionError(
            "all-known incremental pages must not request detail"
        )

        with patch("procurement.tasks.fetcher_for", return_value=list_fetcher):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["parsnamad_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["detail_policy"], "deferred_after_list_boundary")
        self.assertEqual(summary["detail_candidates"], 0)
        self.assertEqual(summary["detail_attempted"], 0)
        list_fetcher.fetch_detail.assert_not_called()

    def test_transient_detail_failure_preserves_rich_semantics_and_fresh_list_fields(self):
        connector = ProcurementConnector.objects.get(key="parsnamad_inquiries")
        self._seed_known(
            connector,
            "970001",
            "عنوان فهرست قدیمی",
            province="تهران",
            published_raw="1405/05/28",
            detail={
                "detail_status": "enriched",
                "title": "عنوان جزئیات قدیمی",
                "province": "قم",
                "published_raw": "1405/05/20",
                "description": "شرح غنی قبلی",
                "deadline_raw": "1405/06/12",
                "event_status": "EventScheduled",
            },
        )
        self._seed_known(connector, "970002", "استعلام شناخته شده دو")
        self._seed_known(connector, "970003", "استعلام شناخته شده سه")

        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.QUEUED,
            include_details=True,
            page_cap=5,
        )
        run.connectors.add(connector)

        events = []
        list_fetcher = Mock()
        pages = [
            ("970001", "عنوان تازه فهرست", 1, "اصفهان", "1405/05/29"),
            ("970002", "استعلام شناخته شده دو", 2, "تهران", "1405/05/29"),
            ("970003", "استعلام شناخته شده سه", 3, "تهران", "1405/05/29"),
        ]

        def fetch_list(page_number, url):
            events.append(f"list-{page_number}")
            record_id, title, page, province, published_raw = pages[page_number - 1]
            return self._fetched(
                url,
                self._notice_html(
                    record_id,
                    title,
                    page,
                    province=province,
                    published_raw=published_raw,
                ),
            )

        list_fetcher.fetch_list.side_effect = fetch_list
        detail_fetcher = Mock()

        def fetch_detail(url):
            events.append("detail")
            return self._fetched(url, "<html><body>temporary detail response</body></html>")

        detail_fetcher.fetch_detail.side_effect = fetch_detail

        with patch(
            "procurement.tasks.fetcher_for",
            side_effect=[list_fetcher, detail_fetcher],
        ):
            result = run_extraction(str(run.id))

        run.refresh_from_db()
        summary = run.summary["connectors"]["parsnamad_inquiries"]
        self.assertEqual(result["status"], ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS)
        self.assertEqual(summary["completeness"], "complete")
        self.assertEqual(summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(summary["detail_candidates"], 1)
        self.assertEqual(summary["detail_attempted"], 1)
        self.assertEqual(summary["detail_enriched"], 0)
        self.assertEqual(summary["detail_failed"], 1)
        self.assertEqual(events, ["list-1", "list-2", "list-3", "detail"])

        source_notice = SourceNotice.objects.get(
            connector=connector,
            source_record_id="970001",
        )
        self.assertEqual(source_notice.title_raw, "عنوان تازه فهرست")
        self.assertEqual(source_notice.province_raw, "اصفهان")
        self.assertEqual(source_notice.published_at_raw, "1405/05/29")
        self.assertEqual(source_notice.deadline_raw, "1405/06/12")
        self.assertEqual(source_notice.detail_status, SourceNotice.DetailStatus.ENRICHED)
        preserved_detail = source_notice.raw_payload["detail"]
        self.assertEqual(preserved_detail["description"], "شرح غنی قبلی")
        self.assertNotIn("title", preserved_detail)
        self.assertNotIn("province", preserved_detail)
        self.assertNotIn("published_raw", preserved_detail)
