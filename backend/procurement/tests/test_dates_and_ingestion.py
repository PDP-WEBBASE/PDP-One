from datetime import datetime, timedelta
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
        fixed_now = timezone.make_aware(
            datetime(2026, 7, 22, 10, 0, 0),
            timezone.get_current_timezone(),
        )
        now.return_value = fixed_now
        parsed, metadata = parse_deadline_value("۴ روز و ۸ ساعت")
        self.assertEqual(parsed, fixed_now + timedelta(days=4, hours=8))
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

    def test_page_movement_and_raw_capture_drift_do_not_create_semantic_update(self):
        first = self.parsed_notice()
        first.raw_payload = {"source_marker": "page-one"}
        source, _, status = ingest_parsed_notice(
            self.connector,
            first,
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        self.assertEqual(source.revisions.count(), 1)

        moved = self.parsed_notice()
        moved.source_url = "https://www.hezarehinfo.net/tenders/-%21/page-2"
        moved.raw_payload = {"source_marker": "page-two"}
        source, _, status = ingest_parsed_notice(
            self.connector,
            moved,
            run=self.run,
            page_number=2,
        )

        source.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.revisions.count(), 1)
        self.assertEqual(source.source_url, moved.source_url)
        self.assertEqual(source.raw_payload["list"]["source_marker"], "page-two")
        latest_item = self.run.items.order_by("-created_at").first()
        self.assertEqual(latest_item.status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(latest_item.changed_fields, [])

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


class SetadRelativeCountdownIngestionTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="setad_inquiries")
        self.run = ExtractionRun.objects.create(status=ExtractionRun.Status.RUNNING)
        self.run.connectors.add(self.connector)
        self.base_time = timezone.make_aware(
            datetime(2026, 8, 20, 10, 0, 0),
            timezone.get_current_timezone(),
        )

    def parsed_notice(self, deadline_raw: str, *, title: str = "خدمات مطالعات و طراحی شبکه برق"):
        return ParsedNotice(
            source_record_id="۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱",
            source_url="https://eproc.setadiran.ir/eproc/needs.do",
            detail_url=(
                "https://eproc.setadiran.ir/eproc/needDetailsInfoModal-load.do?"
                "reqId=7279593&domainType=1432&needId=5239285"
            ),
            source_declared_type="inquiry",
            content_detected_type="inquiry",
            type_resolution_status="resolved",
            title=title,
            employer="شرکت برق منطقه ای",
            province="اصفهان",
            published_raw="۱۴۰۵/۰۵/۲۹",
            deadline_raw=deadline_raw,
            summary="انتخاب تامین کننده | خدمات | فعالیت های حرفه ای، علمی و فنی",
            description=title,
            notice_number="۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱",
            detail_status="not_requested",
            position=1,
            metadata={
                "setad_channel": "eproc",
                "need_type": "انتخاب تامین کننده",
                "category": "خدمات",
                "relative_deadline": deadline_raw,
                "req_id": "7279593",
                "domain_type": "1432",
                "need_id": "5239285",
            },
            raw_payload={
                "need_number": "۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱",
                "title": title,
                "employer": "شرکت برق منطقه ای",
                "province": "اصفهان",
                "published_raw": "۱۴۰۵/۰۵/۲۹",
                "deadline_raw": deadline_raw,
                "req_id": "7279593",
                "domain_type": "1432",
                "need_id": "5239285",
            },
        )

    def ingest_at(self, observed_at, parsed_notice):
        with patch("procurement.ingestion.timezone.now", return_value=observed_at):
            return ingest_parsed_notice(
                self.connector,
                parsed_notice,
                run=self.run,
                page_number=1,
            )

    def test_natural_setad_countdown_progression_remains_duplicate_and_preserves_deadline(self):
        source, notice, status = self.ingest_at(
            self.base_time,
            self.parsed_notice("۴ روز و ۸ ساعت"),
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        original_hash = source.content_hash
        original_deadline = notice.submission_deadline
        self.assertEqual(source.revisions.count(), 1)

        # Emulate an existing pre-safeguard Runtime record without the new internal
        # marker. The first post-deploy observation must bootstrap from its revision.
        legacy_raw_payload = dict(source.raw_payload)
        legacy_raw_payload.pop("_pdp", None)
        source.raw_payload = legacy_raw_payload
        source.save(update_fields=["raw_payload", "updated_at"])

        source, notice, status = self.ingest_at(
            self.base_time + timedelta(hours=1),
            self.parsed_notice("۴ روز و ۷ ساعت"),
        )
        source.refresh_from_db()
        notice.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.content_hash, original_hash)
        self.assertEqual(source.deadline_raw, "۴ روز و ۷ ساعت")
        self.assertEqual(source.revisions.count(), 1)
        self.assertIn("_pdp", source.raw_payload)
        self.assertEqual(notice.submission_deadline, original_deadline)
        self.assertEqual(
            notice.date_metadata["deadline"]["stability_source"],
            "preserved_progressing_relative_deadline",
        )

        source, notice, status = self.ingest_at(
            self.base_time + timedelta(hours=2),
            self.parsed_notice("۴ روز و ۶ ساعت"),
        )
        source.refresh_from_db()
        notice.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.content_hash, original_hash)
        self.assertEqual(source.deadline_raw, "۴ روز و ۶ ساعت")
        self.assertEqual(source.revisions.count(), 1)
        self.assertEqual(notice.submission_deadline, original_deadline)

    def test_real_setad_deadline_extension_remains_semantic_update(self):
        source, notice, status = self.ingest_at(
            self.base_time,
            self.parsed_notice("۴ روز و ۸ ساعت"),
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        original_hash = source.content_hash
        original_deadline = notice.submission_deadline

        source, notice, status = self.ingest_at(
            self.base_time + timedelta(hours=1),
            self.parsed_notice("۵ روز و ۷ ساعت"),
        )
        source.refresh_from_db()
        notice.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.UPDATED)
        self.assertNotEqual(source.content_hash, original_hash)
        self.assertEqual(source.revisions.count(), 2)
        self.assertGreater(notice.submission_deadline, original_deadline)

    def test_other_semantic_change_is_updated_during_natural_countdown(self):
        source, _, status = self.ingest_at(
            self.base_time,
            self.parsed_notice("۴ روز و ۸ ساعت"),
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        original_hash = source.content_hash

        source, notice, status = self.ingest_at(
            self.base_time + timedelta(hours=1),
            self.parsed_notice(
                "۴ روز و ۷ ساعت",
                title="خدمات مطالعات و طراحی شبکه برق ـ اصلاحیه",
            ),
        )
        source.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.UPDATED)
        self.assertNotEqual(source.content_hash, original_hash)
        self.assertEqual(source.revisions.count(), 2)
        self.assertEqual(notice.title, "خدمات مطالعات و طراحی شبکه برق ـ اصلاحیه")
