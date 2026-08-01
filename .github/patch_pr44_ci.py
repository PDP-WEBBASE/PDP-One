from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "backend/procurement/analysis_run_service_v2.py",
    '''def _procurement_table_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_type = 'BASE TABLE'
              AND table_name LIKE 'procurement_%'
            ORDER BY table_name
            """
        )
        table_names = [row[0] for row in cursor.fetchall()]
        for table_name in table_names:
            cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}")
            counts[table_name] = int(cursor.fetchone()[0])
    return counts
''',
    '''def _procurement_table_counts() -> dict[str, int]:
    """Count procurement tables on PostgreSQL and the SQLite test backend."""
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                  AND table_name LIKE 'procurement_%'
                ORDER BY table_name
                """
            )
            table_names = [row[0] for row in cursor.fetchall()]
        else:
            table_names = sorted(
                table_name
                for table_name in connection.introspection.table_names(cursor)
                if table_name.startswith("procurement_")
            )
        for table_name in table_names:
            cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}")
            counts[table_name] = int(cursor.fetchone()[0])
    return counts
''',
)

replace_once(
    "backend/procurement/tasks_automation.py",
    '''    result = dispatch_scheduled_analysis_run()
    return {**result, "persistent_run": True, "draft_only": True, "human_review_required": True}
''',
    '''    result = dispatch_scheduled_analysis_run()
    return {
        **result,
        "created": int(bool(result.get("dispatched"))),
        "persistent_run": True,
        "draft_only": True,
        "human_review_required": True,
    }
''',
)

(ROOT / "backend/procurement/tests/test_automation_settings.py").write_text(
    '''from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementConnector
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun
from procurement.tasks_automation import dispatch_due_extraction


class ProcurementAutomationSettingsTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="system-admin",
            password="test-pass",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.settings = ProcurementAutomationSettings.objects.get(key="default")

    def test_guarded_automation_is_enabled_once_with_persistent_hourly_workflow(self):
        self.assertTrue(self.settings.enabled)
        self.assertEqual(self.settings.cadence, ProcurementAutomationSettings.Cadence.HOURLY)
        self.assertEqual(self.settings.interval_minutes, 60)
        self.assertEqual(str(self.settings.daily_time)[:5], "07:00")
        self.assertEqual(self.settings.manual_command, "PDP")
        self.assertEqual(self.settings.analysis_delay_minutes, 0)
        self.assertIsNotNone(self.settings.next_extraction_at)

    def test_daily_schedule_requires_time(self):
        response = self.client.patch(
            f"/api/v1/procurement/automation-settings/{self.settings.id}/",
            {"enabled": True, "cadence": "daily", "daily_time": None},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_hourly_schedule_sets_next_run_and_keeps_pdp_command(self):
        response = self.client.patch(
            f"/api/v1/procurement/automation-settings/{self.settings.id}/",
            {
                "enabled": True,
                "cadence": "hourly",
                "interval_minutes": 60,
                "analysis_delay_minutes": 0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["manual_command"], "PDP")
        self.assertIsNotNone(response.data["next_extraction_at"])

    @patch("procurement.tasks_automation.run_extraction.delay")
    def test_dispatch_uses_only_enabled_connectors_and_requests_draft_analysis(self, mocked_delay):
        ProcurementConnector.objects.filter(key="parsnamad_inquiries").update(enabled=False)
        self.settings.enabled = True
        self.settings.cadence = ProcurementAutomationSettings.Cadence.HOURLY
        self.settings.interval_minutes = 60
        self.settings.next_extraction_at = timezone.now()
        self.settings.save()

        with self.captureOnCommitCallbacks(execute=True):
            result = dispatch_due_extraction()
        self.assertTrue(result["dispatched"])
        self.assertNotIn("parsnamad_inquiries", result["connector_keys"])
        run = ExtractionRun.objects.get(pk=result["run_id"])
        self.assertEqual(run.trigger, ExtractionRun.Trigger.SCHEDULED)
        self.assertTrue(run.analyze_after_success)
        self.assertFalse(run.connectors.filter(key="parsnamad_inquiries").exists())
        mocked_delay.assert_called_once_with(str(run.id))
''',
    encoding="utf-8",
)

(ROOT / "backend/procurement/tests/test_guarded_automation.py").write_text(
    '''from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import AuditEvent
from procurement.analysis_run_service import initialize_run
from procurement.models import ProcurementConnector, ProcurementSource
from procurement.models_analysis import AnalysisContextSnapshot, AnalysisRequest
from procurement.models_analysis_runs import ProcurementAnalysisRun
from procurement.models_automation import ProcurementAutomationSettings
from procurement.models_extraction import ExtractionRun
from procurement.tasks_automation import (
    BOOTSTRAP_ACTION,
    bootstrap_guarded_automation,
    dispatch_due_analysis_requests,
    dispatch_due_extraction,
)


class GuardedAutomationTests(TestCase):
    def setUp(self):
        AuditEvent.objects.filter(action=BOOTSTRAP_ACTION).delete()
        ProcurementAutomationSettings.objects.filter(key="default").delete()
        ProcurementConnector.objects.update(enabled=False)
        ProcurementSource.objects.update(enabled=False)
        self.source = ProcurementSource.objects.create(
            key="automation-source",
            name="منبع زمان‌بندی",
            base_url="https://example.com",
            enabled=True,
        )
        self.connector = ProcurementConnector.objects.create(
            source=self.source,
            key="automation-tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            list_url_template="https://example.com/page-{page}",
            enabled=True,
            status=ProcurementConnector.Status.ACTIVE,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=81,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر زمان‌بندی‌شده",
            base_instructions="فقط پیش‌نویس ایجاد شود.",
            analysis_prompt="تحلیل کن.",
        )

    def test_bootstrap_is_one_time_and_respects_later_disable(self):
        first = bootstrap_guarded_automation()
        self.assertTrue(first["changed"])
        settings = ProcurementAutomationSettings.objects.get(key="default")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.cadence, ProcurementAutomationSettings.Cadence.HOURLY)
        self.assertEqual(settings.interval_minutes, 60)
        self.assertEqual(settings.analysis_delay_minutes, 0)
        settings.enabled = False
        settings.save(update_fields=["enabled", "updated_at"])

        second = bootstrap_guarded_automation()
        settings.refresh_from_db()
        self.assertFalse(second["changed"])
        self.assertFalse(settings.enabled)

    def test_due_extraction_is_incremental_and_requests_draft_analysis(self):
        bootstrap_guarded_automation()
        settings = ProcurementAutomationSettings.objects.get(key="default")
        settings.next_extraction_at = timezone.now() - timedelta(minutes=1)
        settings.save(update_fields=["next_extraction_at", "updated_at"])

        with self.captureOnCommitCallbacks(execute=False):
            result = dispatch_due_extraction.run()
        self.assertTrue(result["dispatched"])
        run = ExtractionRun.objects.get(pk=result["run_id"])
        self.assertEqual(run.trigger, ExtractionRun.Trigger.SCHEDULED)
        self.assertEqual(run.mode, ExtractionRun.Mode.INCREMENTAL)
        self.assertTrue(run.analyze_after_success)
        self.assertEqual(list(run.connectors.values_list("key", flat=True)), [self.connector.key])

    @patch("procurement.tasks_analysis_runs.initialize_analysis_run_task.delay")
    def test_scheduled_dispatch_creates_one_persistent_run_and_then_continues_it(self, mocked_delay):
        bootstrap_guarded_automation()

        first = dispatch_due_analysis_requests.run()
        second = dispatch_due_analysis_requests.run()

        self.assertEqual(first["created"], 1)
        self.assertTrue(first["persistent_run"])
        self.assertTrue(first["draft_only"])
        self.assertEqual(second["created"], 0)
        self.assertTrue(second["continued"])
        self.assertEqual(first["run_id"], second["run_id"])
        run = ProcurementAnalysisRun.objects.get(pk=first["run_id"])
        self.assertEqual(run.trigger, ProcurementAnalysisRun.Trigger.SCHEDULED)
        self.assertEqual(run.run_type, ProcurementAnalysisRun.RunType.INCREMENTAL)
        self.assertTrue(run.metadata["draft_only"])
        self.assertTrue(run.metadata["human_review_required"])
        mocked_delay.assert_called_once_with(str(run.id))

    @patch("procurement.tasks_analysis_runs.initialize_analysis_run_task.delay")
    def test_empty_persistent_run_finishes_as_no_changes(self, mocked_delay):
        bootstrap_guarded_automation()
        result = dispatch_due_analysis_requests.run()
        run = ProcurementAnalysisRun.objects.get(pk=result["run_id"])

        initialize_run(str(run.id), actor="test")
        run.refresh_from_db()

        self.assertEqual(run.status, ProcurementAnalysisRun.Status.NO_CHANGES)
        self.assertEqual(run.counters["total"], 0)
        self.assertEqual(run.analysis_request.status, AnalysisRequest.Status.NO_CHANGES)
        mocked_delay.assert_called_once_with(str(run.id))
''',
    encoding="utf-8",
)

print("PR #44 CI compatibility patch applied")
