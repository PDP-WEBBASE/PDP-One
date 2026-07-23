import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from procurement.models import (
    NoticeSourceLink,
    ProcurementConnector,
    ProcurementNotice,
    SourceNotice,
)
from procurement.models_extraction import ExtractionRun, ExtractionRunItem


class ParsNamadTenderRepairTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="parsnamad_tenders")
        self.previous_run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
            page_cap=5,
            summary={
                "connectors": {
                    "parsnamad_tenders": {
                        "status": "succeeded",
                        "pages": 5,
                        "seen": 250,
                        "new": 250,
                        "updated": 0,
                        "duplicate": 0,
                        "failed": 0,
                        "warnings": 0,
                    }
                },
                "skipped_disabled_connectors": [],
            },
        )
        self.previous_run.connectors.add(
            *ProcurementConnector.objects.filter(
                key__in=[
                    "hezareh_tenders",
                    "hezareh_inquiries",
                    "parsnamad_tenders",
                    "parsnamad_inquiries",
                ]
            )
        )
        now = timezone.now()
        self.source_notice = SourceNotice.objects.create(
            connector=self.connector,
            source_record_id="wrong-1",
            source_url="https://www.parsnamaddata.com/tenders/page/1",
            source_declared_type="tender",
            title_raw="استعلام خرید کالای نمونه",
            province_raw="تهران",
            raw_payload={},
            content_hash="a" * 64,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="استعلام خرید کالای نمونه",
            first_seen_at=now,
            last_seen_at=now,
        )
        NoticeSourceLink.objects.create(
            procurement_notice=self.notice,
            source_notice=self.source_notice,
            confidence=100,
        )
        ExtractionRunItem.objects.create(
            run=self.previous_run,
            connector=self.connector,
            source_notice=self.source_notice,
            source_record_id=self.source_notice.source_record_id,
            page_number=1,
            position=1,
            status=ExtractionRunItem.Status.NEW,
        )

    def fake_successful_run(self, run_id):
        run = ExtractionRun.objects.get(pk=run_id)
        run.status = ExtractionRun.Status.SUCCEEDED
        run.pages_processed = 5
        run.records_seen = 50
        run.records_new = 50
        run.summary = {
            "connectors": {
                "parsnamad_tenders": {
                    "status": "succeeded",
                    "pages": 5,
                    "seen": 50,
                    "new": 50,
                    "updated": 0,
                    "duplicate": 0,
                    "failed": 0,
                    "warnings": 0,
                }
            }
        }
        run.save(
            update_fields=[
                "status",
                "pages_processed",
                "records_seen",
                "records_new",
                "summary",
                "updated_at",
            ]
        )
        return {"run_id": str(run.id), "status": run.status, "summary": run.summary}

    @patch(
        "procurement.management.commands.repair_and_retest_parsnamad_tenders.run_extraction",
        autospec=True,
    )
    def test_cleanup_finds_overwritten_run_and_removes_only_safe_records(
        self, run_extraction
    ):
        run_extraction.side_effect = self.fake_successful_run
        stdout = StringIO()

        call_command(
            "repair_and_retest_parsnamad_tenders",
            pages=5,
            stdout=stdout,
        )

        self.assertFalse(SourceNotice.objects.filter(pk=self.source_notice.pk).exists())
        self.assertFalse(ProcurementNotice.objects.filter(pk=self.notice.pk).exists())
        self.previous_run.refresh_from_db()
        cleanup = self.previous_run.summary["parsnamad_tender_cleanup"]
        self.assertEqual(cleanup["removed_source_notices"], 1)
        self.assertEqual(cleanup["removed_procurement_notices"], 1)
        self.assertEqual(cleanup["skipped"], [])

        self.connector.refresh_from_db()
        self.assertEqual(
            self.connector.list_url_template,
            "https://www.parsnamaddata.com/tender/page-{page}",
        )
        self.assertEqual(self.connector.parser_version, "parsnamad-tenders-v2")

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["retest_status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(payload["connector"]["summary"]["pages"], 5)
