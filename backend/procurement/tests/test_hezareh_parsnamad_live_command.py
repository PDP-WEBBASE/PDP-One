import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from procurement.models import ProcurementConnector
from procurement.models_extraction import ExtractionRun


class HezarehParsnamadLiveTestCommandTests(TestCase):
    enabled_connector_keys = [
        "hezareh_tenders",
        "hezareh_inquiries",
        "parsnamad_inquiries",
    ]

    def fake_successful_run(self, run_id):
        run = ExtractionRun.objects.get(pk=run_id)
        connector_summaries = {
            key: {
                "status": "succeeded",
                "pages": 5,
                "seen": 12,
                "new": 12,
                "updated": 0,
                "duplicate": 0,
                "failed": 0,
                "warnings": 0,
            }
            for key in run.connectors.values_list("key", flat=True)
        }
        connector_count = run.connectors.count()
        run.status = ExtractionRun.Status.SUCCEEDED
        run.pages_processed = 5 * connector_count
        run.records_seen = 12 * connector_count
        run.records_new = 12 * connector_count
        run.summary = {
            **(run.summary or {}),
            "connectors": connector_summaries,
            "skipped_disabled_connectors": [],
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
        "procurement.management.commands.test_hezareh_parsnamad_connectors.run_extraction",
        autospec=True,
    )
    def test_command_tests_only_enabled_connectors(self, run_extraction):
        run_extraction.side_effect = self.fake_successful_run
        stdout = StringIO()
        stderr = StringIO()

        call_command(
            "test_hezareh_parsnamad_connectors",
            pages=5,
            stdout=stdout,
            stderr=stderr,
        )

        run = ExtractionRun.objects.get()
        self.assertEqual(run.page_cap, 5)
        self.assertFalse(run.include_details)
        self.assertFalse(run.analyze_after_success)
        self.assertEqual(
            set(run.connectors.values_list("key", flat=True)),
            set(self.enabled_connector_keys),
        )
        self.assertFalse(
            ProcurementConnector.objects.get(key="parsnamad_tenders").enabled
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["run_status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(payload["page_cap_per_connector"], 5)
        self.assertEqual(payload["configured_connector_count"], 4)
        self.assertEqual(payload["tested_connector_count"], 3)
        self.assertEqual(payload["maximum_page_attempts"], 15)
        self.assertEqual(
            payload["skipped_disabled_connector_keys"],
            ["parsnamad_tenders"],
        )
        self.assertFalse(payload["setad_included"])
        self.assertEqual(len(payload["connectors"]), 4)
        disabled_report = next(
            item for item in payload["connectors"] if item["key"] == "parsnamad_tenders"
        )
        self.assertFalse(disabled_report["tested"])
        self.assertEqual(disabled_report["requested_pages"], 0)

    def test_command_rejects_more_than_ten_pages(self):
        with self.assertRaises(CommandError):
            call_command("test_hezareh_parsnamad_connectors", pages=11)
