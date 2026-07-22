import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_extraction import ExtractionRun


class SetadLiveTestCommandTests(TestCase):
    def fake_successful_run(self, run_id):
        run = ExtractionRun.objects.get(pk=run_id)
        connector_summaries = {
            key: {
                "status": "succeeded",
                "pages": 2,
                "seen": 3,
                "new": 3,
                "updated": 0,
                "duplicate": 0,
                "failed": 0,
                "warnings": 0,
            }
            for key in run.connectors.values_list("key", flat=True)
        }
        run.status = ExtractionRun.Status.SUCCEEDED
        run.pages_processed = 4
        run.records_seen = 6
        run.records_new = 6
        run.summary = {"connectors": connector_summaries, "skipped_disabled_connectors": []}
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
        "procurement.management.commands.test_setad_connectors.run_extraction",
        autospec=True,
    )
    def test_command_activates_and_runs_both_public_connectors(self, run_extraction):
        run_extraction.side_effect = self.fake_successful_run
        stdout = StringIO()
        stderr = StringIO()

        call_command(
            "test_setad_connectors",
            pages=2,
            connector="all",
            stdout=stdout,
            stderr=stderr,
        )

        source = ProcurementSource.objects.get(key="setad")
        self.assertTrue(source.enabled)
        self.assertEqual(source.status, ProcurementSource.Status.ACTIVE)
        connectors = ProcurementConnector.objects.filter(
            key__in=["setad_tenders", "setad_inquiries"]
        )
        self.assertEqual(connectors.filter(enabled=True).count(), 2)
        self.assertEqual(
            connectors.filter(status=ProcurementConnector.Status.ACTIVE).count(),
            2,
        )

        run = ExtractionRun.objects.get()
        self.assertEqual(run.page_cap, 2)
        self.assertFalse(run.include_details)
        self.assertFalse(run.analyze_after_success)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["run_status"], ExtractionRun.Status.SUCCEEDED)
        self.assertEqual(payload["totals"]["records_seen"], 6)
        self.assertEqual(len(payload["connectors"]), 2)

    def test_command_rejects_more_than_five_pages(self):
        with self.assertRaises(CommandError):
            call_command("test_setad_connectors", pages=6)
