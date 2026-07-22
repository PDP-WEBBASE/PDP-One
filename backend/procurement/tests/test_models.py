from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from procurement.models import (
    ProcurementCase,
    ProcurementConnector,
    ProcurementNotice,
    ProcurementSource,
    SourceNotice,
    SourceNoticeRevision,
)


class ProcurementSeedTests(TestCase):
    def test_initial_sources_and_connectors_are_seeded(self):
        self.assertEqual(ProcurementSource.objects.count(), 3)
        self.assertEqual(ProcurementConnector.objects.count(), 6)

        self.assertTrue(ProcurementSource.objects.get(key="hezareh").enabled)
        self.assertTrue(ProcurementSource.objects.get(key="parsnamad").enabled)

        setad = ProcurementSource.objects.get(key="setad")
        self.assertTrue(setad.enabled)
        self.assertEqual(setad.status, ProcurementSource.Status.ACTIVE)
        self.assertEqual(setad.base_url, "https://setadiran.ir")
        self.assertEqual(
            setad.configuration["public_hosts"],
            ["etend.setadiran.ir", "eproc.setadiran.ir"],
        )
        self.assertEqual(setad.configuration["activation_approved_at"], "2026-07-23")

        tenders = ProcurementConnector.objects.get(key="setad_tenders")
        inquiries = ProcurementConnector.objects.get(key="setad_inquiries")
        self.assertTrue(tenders.enabled)
        self.assertTrue(inquiries.enabled)
        self.assertEqual(tenders.status, ProcurementConnector.Status.ACTIVE)
        self.assertEqual(inquiries.status, ProcurementConnector.Status.ACTIVE)
        self.assertEqual(tenders.parser_version, "setad-etend-json-v1")
        self.assertEqual(inquiries.parser_version, "setad-eproc-needs-html-v1")
        self.assertFalse(tenders.requires_browser)
        self.assertFalse(inquiries.requires_browser)
        self.assertFalse(tenders.supports_detail)
        self.assertFalse(inquiries.supports_detail)

    def test_connector_type_is_unique_per_source(self):
        source = ProcurementSource.objects.get(key="hezareh")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProcurementConnector.objects.create(
                source=source,
                key="hezareh_tenders_duplicate",
                notice_type=ProcurementConnector.NoticeType.TENDER,
                list_url_template="https://example.invalid/page-{page}",
            )


class ProcurementRevisionTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        now = timezone.now()
        self.source_notice = SourceNotice.objects.create(
            connector=self.connector,
            source_record_id="10950416",
            source_url="https://www.hezarehinfo.net/tenders/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/tenders/nid10950416",
            source_declared_type=ProcurementConnector.NoticeType.TENDER,
            title_raw="مناقصه نمونه",
            content_hash="a" * 64,
            raw_payload={"title": "مناقصه نمونه"},
            first_seen_at=now,
            last_seen_at=now,
        )

    def test_revision_number_is_unique_per_source_notice(self):
        SourceNoticeRevision.objects.create(
            source_notice=self.source_notice,
            revision_number=1,
            content_hash="a" * 64,
            raw_payload={},
            parsed_payload={},
            parser_version="hezareh-tenders-v1",
            captured_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SourceNoticeRevision.objects.create(
                source_notice=self.source_notice,
                revision_number=1,
                content_hash="b" * 64,
                raw_payload={},
                parsed_payload={},
                parser_version="hezareh-tenders-v1",
                captured_at=timezone.now(),
            )

    def test_case_protects_selected_notice_from_retention(self):
        now = timezone.now()
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه نمونه",
            first_seen_at=now,
            last_seen_at=now,
        )
        case = ProcurementCase.objects.create(notice=notice)
        self.assertTrue(case.protected_from_retention)
