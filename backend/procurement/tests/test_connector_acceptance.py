from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import (
    NoticeSourceLink,
    ProcurementConnector,
    ProcurementNotice,
    SourceNotice,
)
from procurement.models_extraction import ExtractionPage, ExtractionRun, ExtractionRunItem
from procurement.tasks_acceptance import repair_stale_extraction_runs


class ConnectorAcceptanceApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="connector-acceptance-manager",
            password="test-pass-123",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("procurement.views_acceptance.run_connector_acceptance.delay")
    def test_start_creates_one_bounded_run_per_active_connector(self, delay):
        response = self.client.post(
            "/api/v1/procurement/connector-acceptance/start/",
            {"page_cap": 3, "lookback_days": 7},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["started"])
        self.assertEqual(len(response.data["runs"]), 5)
        self.assertEqual(ExtractionRun.objects.count(), 5)
        self.assertEqual(delay.call_count, 5)
        for run in ExtractionRun.objects.all():
            self.assertEqual(run.connectors.count(), 1)
            self.assertEqual(run.page_cap, 3)
            self.assertEqual(run.lookback_days, 7)
            self.assertFalse(run.include_details)
        disabled = ProcurementConnector.objects.get(key="parsnamad_tenders")
        self.assertFalse(disabled.enabled)
        self.assertEqual(disabled.status, ProcurementConnector.Status.INACTIVE)

    def test_stale_running_run_is_closed_without_deleting_data(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.RUNNING,
            started_at=timezone.now() - timedelta(hours=2),
        )
        run.connectors.add(connector)
        ExtractionPage.objects.create(
            run=run,
            connector=connector,
            page_number=1,
            url="https://example.test/page-1",
            http_status=200,
            parse_status=ExtractionPage.ParseStatus.SUCCEEDED,
            response_bytes=100,
        )
        ExtractionRun.objects.filter(pk=run.pk).update(updated_at=timezone.now() - timedelta(hours=2))

        result = repair_stale_extraction_runs(max_age_minutes=30)

        run.refresh_from_db()
        self.assertEqual(result["repaired_count"], 1)
        self.assertEqual(run.status, ExtractionRun.Status.FAILED)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.pages.count(), 1)
        self.assertTrue(run.summary["watchdog"]["captured_data_preserved"])
        self.assertEqual(run.errors.count(), 1)

    def test_report_contains_raw_standardized_link_and_duplicate_evidence(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        now = timezone.now()
        suite_id = "a" * 32
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.SUCCEEDED_WITH_WARNINGS,
            started_at=now - timedelta(minutes=1),
            finished_at=now,
            pages_processed=1,
            records_seen=1,
            records_duplicate=1,
            summary={
                "acceptance": {"suite_id": suite_id, "connector_key": connector.key},
                "connectors": {connector.key: {"status": "succeeded_with_warnings", "pages": 1}},
            },
        )
        run.connectors.add(connector)
        source_notice = SourceNotice.objects.create(
            connector=connector,
            source_record_id="acceptance-record-1",
            source_url="https://example.test/source/1",
            detail_url="https://example.test/detail/1",
            source_declared_type=connector.notice_type,
            title_raw="آگهی واقعی آزمون پذیرش",
            employer_raw="کارفرمای آزمون",
            raw_payload={"title": "آگهی واقعی آزمون پذیرش", "source": "hezareh"},
            content_hash="1" * 64,
            first_seen_at=now,
            last_seen_at=now,
        )
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=connector.notice_type,
            title="آگهی واقعی آزمون پذیرش",
            employer_name="کارفرمای آزمون",
            first_seen_at=now,
            last_seen_at=now,
        )
        NoticeSourceLink.objects.create(
            procurement_notice=notice,
            source_notice=source_notice,
        )
        ExtractionRunItem.objects.create(
            run=run,
            connector=connector,
            source_notice=source_notice,
            source_record_id=source_notice.source_record_id,
            page_number=1,
            position=1,
            status=ExtractionRunItem.Status.DUPLICATE,
        )
        ExtractionPage.objects.create(
            run=run,
            connector=connector,
            page_number=1,
            url="https://example.test/page-1",
            http_status=200,
            response_bytes=500,
            content_hash="2" * 64,
            parse_status=ExtractionPage.ParseStatus.WARNING,
        )

        response = self.client.get(
            f"/api/v1/procurement/connector-acceptance/{suite_id}/report/"
        )

        self.assertEqual(response.status_code, 200)
        item = response.data["connectors"][0]
        self.assertTrue(item["evidence"]["source_links_present"])
        self.assertTrue(item["evidence"]["raw_data_present"])
        self.assertTrue(item["evidence"]["standardized_data_present"])
        self.assertEqual(item["counts"]["duplicates"], 1)
        self.assertEqual(item["sample_records"][0]["source_url"], source_notice.source_url)
        self.assertEqual(item["sample_records"][0]["raw_data"]["source"], "hezareh")
        self.assertEqual(item["sample_records"][0]["standardized_data"]["title"], notice.title)
