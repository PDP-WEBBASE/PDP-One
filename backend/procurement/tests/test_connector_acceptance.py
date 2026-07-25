import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_extraction import ExtractionRun
from procurement.tasks_connector_acceptance import (
    _save_report,
    load_latest_connector_acceptance_report,
    recover_stale_extraction_runs,
)


class ConnectorAcceptanceTests(TestCase):
    def setUp(self):
        self.source = ProcurementSource.objects.create(
            key="acceptance-source",
            name="Acceptance Source",
            base_url="https://example.test",
            enabled=True,
        )
        self.connector = ProcurementConnector.objects.create(
            source=self.source,
            key="acceptance_tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            enabled=True,
            list_url_template="https://example.test/page/{page}",
        )

    def test_recover_stale_run_preserves_record_and_marks_cancelled(self):
        run = ExtractionRun.objects.create(status=ExtractionRun.Status.QUEUED)
        run.connectors.add(self.connector)
        stale_created_at = timezone.now() - timedelta(hours=3)
        ExtractionRun.objects.filter(pk=run.pk).update(created_at=stale_created_at)

        closed = recover_stale_extraction_runs(now=timezone.now())

        run.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.CANCELLED)
        self.assertIsNotNone(run.finished_at)
        self.assertIn("stale_worker_run", run.summary)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["run_id"], str(run.id))
        self.assertEqual(closed[0]["connector_keys"], [self.connector.key])

    def test_recent_run_is_not_closed(self):
        run = ExtractionRun.objects.create(status=ExtractionRun.Status.RUNNING, started_at=timezone.now())
        run.connectors.add(self.connector)

        closed = recover_stale_extraction_runs(now=timezone.now())

        run.refresh_from_db()
        self.assertEqual(run.status, ExtractionRun.Status.RUNNING)
        self.assertEqual(closed, [])

    def test_v1_dispatcher_rejects_v2_request(self):
        from procurement.tasks_connector_acceptance import dispatch_connector_acceptance

        with patch(
            "procurement.tasks_connector_acceptance.recover_stale_extraction_runs",
            return_value=[],
        ), patch(
            "procurement.tasks_connector_acceptance._read_json",
            return_value={"enabled": True, "acceptance_version": 2},
        ), patch(
            "procurement.tasks_connector_acceptance.run_connector_acceptance.delay",
            new=MagicMock(),
        ) as delay:
            result = dispatch_connector_acceptance.run()

        self.assertEqual(result, {"dispatched": False, "reason": "not_a_v1_request"})
        delay.assert_not_called()

    def test_compact_report_keeps_requested_acceptance_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            latest = root / "latest.json"
            report = {
                "schema": "pdp-one.connector-acceptance.v1",
                "acceptance_id": "acceptance-test",
                "status": "succeeded",
                "started_at": timezone.now().isoformat(),
                "finished_at": timezone.now().isoformat(),
                "lookback_days": 1,
                "stale_runs_closed": [],
                "report_path": str(root / "acceptance-test.json"),
                "totals": {"pages_processed": 1, "records_seen": 1},
                "connectors": [
                    {
                        "key": "hezareh_tenders",
                        "tested": True,
                        "acceptance": "passed",
                        "run_status": "succeeded",
                        "pages_processed": 1,
                        "records_seen": 1,
                        "records_new": 1,
                        "records_updated": 0,
                        "records_duplicate": 0,
                        "records_failed": 0,
                        "error_count": 0,
                        "pages": [{"page_number": 1, "url": "https://example.test/page/1"}],
                        "raw_samples": [{"source_record_id": "1", "raw_payload": {"title": "raw"}}],
                        "normalized_samples": [{"notice_id": "n1", "title": "normalized"}],
                        "errors": [],
                        "reason": "ok",
                    }
                ],
            }
            with patch("procurement.tasks_connector_acceptance.REPORT_ROOT", root), patch(
                "procurement.tasks_connector_acceptance.LATEST_PATH", latest
            ):
                _save_report(report)
                result = load_latest_connector_acceptance_report(compact=True)

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["connectors"][0]["pages"][0]["page_number"], 1)
            self.assertEqual(
                result["connectors"][0]["raw_samples"][0]["raw_payload"]["title"],
                "raw",
            )
            self.assertEqual(
                result["connectors"][0]["normalized_samples"][0]["title"],
                "normalized",
            )
