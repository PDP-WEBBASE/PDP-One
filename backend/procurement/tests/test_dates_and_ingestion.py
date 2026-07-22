from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from procurement.connectors.types import ParsedNotice
from procurement.dates import parse_date_value, parse_deadline_value
from procurement.ingestion import ingest_parsed_notice
from procurement.models import NoticeSourceLink, ProcurementConnector, ProcurementNotice, SourceNoticeRevision
from procurement.models_extraction import ExtractionRun, ExtractionRunItem


class SourceDateTests(TestCase):
    def test_jalali_date_is_normalized_and_raw_value_is_preserved(self):
        parsed, metadata = parse_date_value("۱۴۰۵/۰۵/۰۵")
        self.assertIsNotNone(parsed)
        self.assertEqual(metadata["raw_value"], "۱۴۰۵/۰۵/۰۵")
        self.assertEqual(metadata["calendar_type"], "jalali")
        self.assertEqual(metadata["parse_status"], "valid")
        self.assertTrue(metadata["normalized_date"].startswith("2026-"))

    def test_gregorian_detail_date_is_supported(self):
        parsed, metadata = parse_deadline_value("2026-07-25T00:00:00")
        self.assertIsNotNone(parsed)
        self.assertTrue(timezone.is_aware(parsed))
        self.assertEqual(metadata["calendar_type"], "gregorian")
        self.assertEqual(metadata["normalized_date"], "2026-07-25")
        self.assertEqual(parsed.hour, 0)

    def test_jalali_deadline_preserves_exact_time(self):
        parsed, metadata = parse_deadline_value("1405/05/20 19:00:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.hour, 19)
        self.assertEqual(parsed.minute, 0)
        self.assertEqual(metadata["calendar_type"], "jalali")
        self.assertIn("normalized_datetime", metadata)

    @patch("procurement.dates.timezone.now")
    def test_relative_deadline_is_converted_from_persian_duration(self, now):
        fixed_now = timezone.now()
        now.return_value = fixed_now
        parsed, metadata = parse_deadline_value("۴ روز و ۸ ساعت")
        self.assertEqual(parsed, fixed_now + timezone.timedelta(days=4, hours=8))
        self.assertEqual(metadata["calendar_type"], "relative_duration")
        self.assertEqual(metadata["relative_seconds"], 374400)

    def test_non_date_text_is_kept_as_invalid_metadata(self):
        parsed, metadata = parse_date_value("پس از دریافت اسناد")
        self.assertIsNone(parsed)
        self.assertEqual(metadata["parse_status"], "invalid")
        self.assertEqual(metadata["raw_value"], "پس از دریافت اسناد")


class NoticeIngestionTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        self.run = ExtractionRun.objects.create(status=ExtractionRun.Status.RUNNING)
        self.run.connectors.add(self.connector)

    def parsed_notice(self, title="مناقصه طراحی ساختمان"):
        return ParsedNotice(
            source_record_id="10950416",
            source_url="https://www.hezarehinfo.net/tenders/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/tenders/nid10950416",
            source_declared_type="tender",
            content_detected_type="tender",
            type_resolution_status="resolved",
            title=title,
            province="تهران",
            deadline_raw="1405/05/18",
            position=1,
        )

    def test_new_duplicate_and_updated_records_create_expected_revisions(self):
        source, notice, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(),
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        self.assertEqual(source.revisions.count(), 1)
        self.assertEqual(notice.processing_status, ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS)

        source, notice, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(),
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.revisions.count(), 1)

        source, notice, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(title="مناقصه طراحی ساختمان ـ تمدید مهلت"),
            run=self.run,
            page_number=2,
        )
        self.assertEqual(status, ExtractionRunItem.Status.UPDATED)
        self.assertEqual(source.revisions.count(), 2)
        self.assertEqual(notice.title, "مناقصه طراحی ساختمان ـ تمدید مهلت")

    def test_type_conflict_is_saved_in_detected_view_and_marked_for_review(self):
        parsed = self.parsed_notice(title="استعلام خدمات طراحی")
        parsed.content_detected_type = "inquiry"
        parsed.type_resolution_status = "needs_review"
        _, notice, _ = ingest_parsed_notice(self.connector, parsed)

        self.assertEqual(notice.resolved_notice_type, ProcurementNotice.NoticeType.INQUIRY)
        self.assertEqual(
            notice.type_resolution_status,
            ProcurementNotice.TypeResolutionStatus.NEEDS_REVIEW,
        )
        self.assertEqual(notice.processing_status, ProcurementNotice.ProcessingStatus.NORMALIZED)

    def test_exact_notice_number_and_employer_can_link_two_sources(self):
        inquiry_connector = ProcurementConnector.objects.get(key="hezareh_inquiries")
        other_connector = ProcurementConnector.objects.get(key="parsnamad_inquiries")
        first = ParsedNotice(
            source_record_id="H-100",
            source_url="https://www.hezarehinfo.net/inquiries/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/inquiries/nid100",
            source_declared_type="inquiry",
            content_detected_type="inquiry",
            type_resolution_status="resolved",
            title="استعلام خدمات مطالعاتی",
            employer="کارفرمای نمونه",
        )
        second = ParsedNotice(
            source_record_id="P-200",
            source_url="https://www.parsnamaddata.com/inquiries/page/1",
            detail_url="https://www.parsnamaddata.com/tender/200/sample",
            source_declared_type="inquiry",
            content_detected_type="inquiry",
            type_resolution_status="resolved",
            title="استعلام خدمات مطالعاتی",
            employer="کارفرمای نمونه",
        )
        _, notice_one, _ = ingest_parsed_notice(
            inquiry_connector,
            first,
            detail={"notice_number": "ABC-101", "employer": "کارفرمای نمونه"},
        )
        _, notice_two, _ = ingest_parsed_notice(
            other_connector,
            second,
            detail={"notice_number": "ABC-101", "employer": "کارفرمای نمونه"},
        )
        self.assertEqual(notice_one.id, notice_two.id)
        self.assertEqual(NoticeSourceLink.objects.filter(procurement_notice=notice_one).count(), 2)
        self.assertEqual(SourceNoticeRevision.objects.count(), 2)
