from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Contract
from procurement.models import ProcurementCase, ProcurementConnector, ProcurementNotice, ProcurementSource
from procurement.models_extraction import ExtractionRun


class ManagementDashboardTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dashboard-manager", password="pass", is_staff=True)
        self.client.force_authenticate(self.user)
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="فراخوان داشبورد",
            employer_name="کارفرمای داشبورد",
            is_recommended=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        ProcurementCase.objects.create(
            notice=self.notice,
            stage=ProcurementCase.Stage.WON,
            created_by=self.user,
        )
        Contract.objects.create(
            code="CASE-DASHBOARD01",
            title="قرارداد داشبورد",
            employer="کارفرمای داشبورد",
            status=Contract.Status.DRAFT,
            created_by=self.user,
            value_rials=1000000,
        )
        source = ProcurementSource.objects.create(
            key="dashboard-source",
            name="منبع داشبورد",
            base_url="https://example.com",
        )
        connector = ProcurementConnector.objects.create(
            source=source,
            key="dashboard-tenders",
            notice_type=ProcurementConnector.NoticeType.TENDER,
            list_url_template="https://example.com/page-{page}",
        )
        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.SCHEDULED,
            status=ExtractionRun.Status.SUCCEEDED,
            started_at=now,
            finished_at=now,
            records_new=1,
        )
        run.connectors.add(connector)

    def test_dashboard_uses_live_counts_and_connector_sets(self):
        response = self.client.get("/api/v1/procurement/management-dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["uses_live_data_only"])
        self.assertGreaterEqual(response.data["notices"]["recommended"], 1)
        self.assertGreaterEqual(response.data["cases"]["won"], 1)
        self.assertGreaterEqual(response.data["contracts"]["case_generated_drafts"], 1)
        self.assertEqual(response.data["latest_extraction_runs"][0]["connector_keys"], ["dashboard-tenders"])
        self.assertNotIn("sample", response.data)
