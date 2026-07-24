from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from procurement.connectors.types import ParsedNotice, ParsedPage
from procurement.http import FetchedPage
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementNotice, SourceNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


def parsed(record_id: str, published_date, title: str | None = None):
    return ParsedNotice(
        source_record_id=record_id,
        source_url=f"https://example.test/list/{record_id}",
        detail_url="",
        source_declared_type="tender",
        content_detected_type="tender",
        type_resolution_status="resolved",
        title=title or f"مناقصه {record_id}",
        published_raw=published_date.isoformat(),
        position=1,
        raw_payload={"id": record_id},
    )


def fetched(page: int):
    content = f"page-{page}".encode()
    return FetchedPage(
        url=f"https://example.test/page-{page}",
        status_code=200,
        content=content,
        text=content.decode(),
    )


class ExtractionModeTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        self.connector.max_pages = 10
        self.connector.save(update_fields=["max_pages", "updated_at"])

    def execute(self, run, pages):
        fake_fetcher = Mock()
        fake_fetcher.fetch_list.side_effect = [fetched(index + 1) for index in range(len(pages))]
        fake_parser = Mock()
        fake_parser.parse_list.side_effect = pages
        with patch("procurement.tasks.fetcher_for", return_value=fake_fetcher), patch(
            "procurement.tasks.parser_for", return_value=fake_parser
        ):
            return run_extraction(str(run.id))

    def test_first_connector_run_only_ingests_today_and_previous_day(self):
        today = timezone.localdate()
        run = ExtractionRun.objects.create(
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=5,
        )
        run.connectors.add(self.connector)
        pages = [
            ParsedPage(
                notices=[parsed("current", today), parsed("old-mixed", today - timedelta(days=3))],
                reported_current_page=1,
                reported_total_pages=4,
                end_of_results=False,
            ),
            ParsedPage(
                notices=[parsed("old-page", today - timedelta(days=4))],
                reported_current_page=2,
                reported_total_pages=4,
                end_of_results=False,
            ),
        ]

        result = self.execute(run, pages)
        run.refresh_from_db()

        self.assertEqual(result["summary"]["connectors"][self.connector.key]["policy"], "first_run_one_day")
        self.assertEqual(run.records_new, 1)
        self.assertTrue(SourceNotice.objects.filter(source_record_id="current").exists())
        self.assertFalse(SourceNotice.objects.filter(source_record_id="old-mixed").exists())
        self.assertEqual(
            result["summary"]["connectors"][self.connector.key]["stop_reason"],
            "date_boundary_reached",
        )

    def test_incremental_run_stops_after_two_fully_known_pages(self):
        today = timezone.localdate()
        known_page_one = parsed("known-1", today)
        known_page_two = parsed("known-2", today)
        ingest_parsed_notice(self.connector, known_page_one)
        ingest_parsed_notice(self.connector, known_page_two)
        run = ExtractionRun.objects.create(
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=5,
        )
        run.connectors.add(self.connector)
        pages = [
            ParsedPage(notices=[known_page_one], reported_current_page=1, reported_total_pages=8, end_of_results=False),
            ParsedPage(notices=[known_page_two], reported_current_page=2, reported_total_pages=8, end_of_results=False),
        ]

        result = self.execute(run, pages)
        connector_summary = result["summary"]["connectors"][self.connector.key]

        self.assertEqual(connector_summary["policy"], "incremental_known_boundary")
        self.assertEqual(connector_summary["known_boundary_pages"], 2)
        self.assertEqual(connector_summary["stop_reason"], "known_data_boundary_reached")
        self.assertEqual(connector_summary["pages"], 2)

    def test_manual_range_ignores_known_boundary_until_date_cutoff(self):
        today = timezone.localdate()
        known_page_one = parsed("known-1", today)
        known_page_two = parsed("known-2", today)
        ingest_parsed_notice(self.connector, known_page_one)
        ingest_parsed_notice(self.connector, known_page_two)
        run = ExtractionRun.objects.create(
            mode=ExtractionRun.Mode.MANUAL_RANGE,
            lookback_days=7,
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            page_cap=5,
        )
        run.connectors.add(self.connector)
        pages = [
            ParsedPage(notices=[known_page_one], reported_current_page=1, reported_total_pages=8, end_of_results=False),
            ParsedPage(notices=[known_page_two], reported_current_page=2, reported_total_pages=8, end_of_results=False),
            ParsedPage(
                notices=[parsed("outside", today - timedelta(days=8))],
                reported_current_page=3,
                reported_total_pages=8,
                end_of_results=False,
            ),
        ]

        result = self.execute(run, pages)
        connector_summary = result["summary"]["connectors"][self.connector.key]

        self.assertEqual(connector_summary["policy"], "manual_range")
        self.assertEqual(connector_summary["stop_reason"], "date_boundary_reached")
        self.assertEqual(connector_summary["pages"], 3)
        self.assertFalse(SourceNotice.objects.filter(source_record_id="outside").exists())
        self.assertEqual(ProcurementNotice.objects.count(), 2)
