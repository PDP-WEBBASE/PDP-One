from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import AuditEvent
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionPage, ExtractionRun, ExtractionRunItem
from procurement.tasks_automation import (
    STALE_SCHEDULED_EXTRACTION_IDLE_SECONDS,
    dispatch_due_extraction,
)


class StaleExtractionRecoveryTests(TestCase):
    def setUp(self):
        ProcurementAutomationSettings.objects.filter(key="default").delete()
        ProcurementConnector.objects.update(enabled=False)
        ProcurementSource.objects.update(enabled=False)
        self.now = timezone.now().replace(microsecond=0)
        self.source = ProcurementSource.objects.create(
            key="stale-recovery-source",
            name="منبع بازیابی استخراج",
            base_url="https://example.com",
            enabled=True,
        )
        self.connector = ProcurementConnector.objects.create(
            source=self.source,
            key="stale-recovery-tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            list_url_template="https://example.com/page-{page}",
            enabled=True,
            status=ProcurementConnector.Status.ACTIVE,
        )
        self.settings = ProcurementAutomationSettings.objects.create(
            key="default",
            enabled=True,
            cadence=ProcurementAutomationSettings.Cadence.HOURLY,
            interval_minutes=60,
            analysis_delay_minutes=0,
            next_extraction_at=self.now - timedelta(minutes=1),
        )

    def _dispatch(self):
        with patch("procurement.tasks_automation.timezone.now", return_value=self.now):
            with self.captureOnCommitCallbacks(execute=False):
                return dispatch_due_extraction.run()

    def _make_active_run(
        self,
        *,
        status=ExtractionRun.Status.RUNNING,
        trigger=ExtractionRun.Trigger.SCHEDULED,
        mode=ExtractionRun.Mode.INCREMENTAL,
        idle_minutes=70,
    ):
        started_at = None if status == ExtractionRun.Status.QUEUED else self.now - timedelta(hours=2)
        run = ExtractionRun.objects.create(
            trigger=trigger,
            mode=mode,
            status=status,
            started_at=started_at,
        )
        run.connectors.add(self.connector)
        old_activity = self.now - timedelta(minutes=idle_minutes)
        ExtractionRun.objects.filter(pk=run.pk).update(
            created_at=self.now - timedelta(hours=2),
            updated_at=self.now - timedelta(hours=2),
        )
        if status == ExtractionRun.Status.RUNNING:
            page = ExtractionPage.objects.create(
                run=run,
                connector=self.connector,
                page_number=3,
                url="https://example.com/page-3",
                http_status=200,
                parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
                captured_at=old_activity,
            )
            ExtractionPage.objects.filter(pk=page.pk).update(created_at=old_activity, updated_at=old_activity)
            item = ExtractionRunItem.objects.create(
                run=run,
                connector=self.connector,
                source_record_id="REC-1",
                page_number=3,
                position=1,
                status=ExtractionRunItem.Status.NEW,
            )
            ExtractionRunItem.objects.filter(pk=item.pk).update(
                created_at=old_activity,
                updated_at=old_activity,
            )
        run.refresh_from_db()
        return run

    def test_recent_running_extraction_remains_a_hard_conflict(self):
        run = self._make_active_run(idle_minutes=10)

        result = self._dispatch()

        run.refresh_from_db()
        self.assertFalse(result["dispatched"])
        self.assertEqual(result["reason"], "extraction_already_running")
        self.assertEqual(result["blocking_run_ids"], [str(run.id)])
        self.assertEqual(result["recovered_stale_run_ids"], [])
        self.assertEqual(run.status, ExtractionRun.Status.RUNNING)
        self.assertIsNone(run.finished_at)

    def test_stale_scheduled_running_run_is_failed_closed_and_due_run_is_dispatched(self):
        run = self._make_active_run(idle_minutes=70)

        result = self._dispatch()

        run.refresh_from_db()
        self.assertTrue(result["dispatched"])
        self.assertEqual(result["recovered_stale_run_ids"], [str(run.id)])
        self.assertEqual(run.status, ExtractionRun.Status.FAILED)
        self.assertEqual(run.finished_at, self.now)
        self.assertEqual(run.pages_processed, 1)
        self.assertEqual(run.records_seen, 1)
        self.assertEqual(run.records_new, 1)
        recovery = run.summary["stale_recovery"]
        self.assertEqual(recovery["reason"], "scheduled_incremental_idle_timeout")
        self.assertEqual(recovery["previous_status"], ExtractionRun.Status.RUNNING)
        self.assertGreaterEqual(recovery["idle_seconds"], STALE_SCHEDULED_EXTRACTION_IDLE_SECONDS)
        self.assertEqual(recovery["preserved_evidence"]["pages_recorded"], 1)
        self.assertEqual(recovery["preserved_evidence"]["items_recorded"], 1)
        self.assertEqual(recovery["preserved_evidence"]["records_new"], 1)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="procurement.automation.stale_extraction_recovered",
                target_id=str(run.id),
            ).exists()
        )
        fresh = ExtractionRun.objects.get(pk=result["run_id"])
        self.assertEqual(fresh.status, ExtractionRun.Status.QUEUED)
        self.assertEqual(fresh.trigger, ExtractionRun.Trigger.SCHEDULED)
        self.assertEqual(fresh.mode, ExtractionRun.Mode.INCREMENTAL)

    def test_stale_scheduled_queued_run_is_recovered(self):
        run = self._make_active_run(status=ExtractionRun.Status.QUEUED, idle_minutes=70)

        result = self._dispatch()

        run.refresh_from_db()
        self.assertTrue(result["dispatched"])
        self.assertEqual(result["recovered_stale_run_ids"], [str(run.id)])
        self.assertEqual(run.status, ExtractionRun.Status.FAILED)
        self.assertEqual(run.summary["stale_recovery"]["previous_status"], ExtractionRun.Status.QUEUED)
        self.assertEqual(run.summary["stale_recovery"]["preserved_evidence"]["items_recorded"], 0)

    def test_stale_manual_range_run_is_never_auto_recovered(self):
        run = self._make_active_run(
            trigger=ExtractionRun.Trigger.MANUAL,
            mode=ExtractionRun.Mode.MANUAL_RANGE,
            idle_minutes=180,
        )

        result = self._dispatch()

        run.refresh_from_db()
        self.assertFalse(result["dispatched"])
        self.assertEqual(result["reason"], "extraction_already_running")
        self.assertEqual(result["blocking_run_ids"], [str(run.id)])
        self.assertEqual(result["recovered_stale_run_ids"], [])
        self.assertEqual(run.status, ExtractionRun.Status.RUNNING)
        self.assertIsNone(run.finished_at)
