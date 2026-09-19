from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from procurement.performance_metrics import performance_assurance_snapshot


class PerformanceAssuranceFrameworkTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="performance-assurance-user",
            password="test-pass-123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_dashboard_request_records_sanitized_performance_sample(self):
        response = self.client.get("/api/v1/procurement/ui/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Server-Timing", response)
        self.assertIn("X-PDP-Query-Count", response)
        self.assertEqual(response["X-PDP-Performance-Risk"], "hot_path")

        snapshot = performance_assurance_snapshot()
        metric = snapshot["metrics"]["procurement.ui.dashboard.v2"]
        self.assertGreaterEqual(metric["sample_count"], 1)
        last = metric["last_sample"]
        self.assertIn("duration_ms", last)
        self.assertIn("db_ms", last)
        self.assertIn("query_count", last)
        self.assertNotIn("sql", last)
        self.assertNotIn("params", last)
        self.assertNotIn("url", last)

    def test_authenticated_report_exposes_policy_budgets_and_background_state(self):
        self.client.get("/api/v1/procurement/ui/dashboard/")
        response = self.client.get("/api/v1/procurement/performance-assurance/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "pdp-one.performance-assurance.v1")
        self.assertEqual(payload["policy"]["mode"], "risk_based")
        self.assertFalse(payload["policy"]["stress_test_production"])
        self.assertFalse(payload["policy"]["sql_text_recorded"])
        self.assertIn("procurement.ui.notices.v2", payload["metrics"])
        self.assertIn("background_workload", payload)

    def test_direct_list_is_instrumented_as_hot_path(self):
        response = self.client.get("/api/v1/procurement/direct-opportunities/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-PDP-Performance-Risk"], "hot_path")
        snapshot = performance_assurance_snapshot(compact=True)
        self.assertGreaterEqual(
            snapshot["metrics"]["procurement.ui.direct.list"]["sample_count"],
            1,
        )

    def test_anonymous_performance_report_is_not_public(self):
        client = APIClient()
        response = client.get("/api/v1/procurement/performance-assurance/")
        self.assertIn(response.status_code, {401, 403})


    def test_notice_metrics_are_split_by_type_and_workflow(self):
        response = self.client.get(
            "/api/v1/procurement/ui/notices/",
            {"notice_type": "tender", "workflow": "selected", "page": 1, "page_size": 30},
        )
        self.assertEqual(response.status_code, 200)
        snapshot = performance_assurance_snapshot(compact=True)
        key = "procurement.ui.notices.v2.tender.selected"
        self.assertIn(key, snapshot["metrics"])
        self.assertEqual(snapshot["metrics"][key]["risk"], "hot_path")
        self.assertGreaterEqual(snapshot["metrics"][key]["sample_count"], 1)

    def test_notice_metric_dimensions_are_bounded(self):
        response = self.client.get(
            "/api/v1/procurement/ui/notices/",
            {"notice_type": "unexpected", "workflow": "unexpected-value"},
        )
        self.assertEqual(response.status_code, 200)
        snapshot = performance_assurance_snapshot(compact=True)
        self.assertIn("procurement.ui.notices.v2.all.recent", snapshot["metrics"])
        self.assertNotIn("unexpected-value", " ".join(snapshot["metrics"].keys()))

    def test_direct_metrics_are_split_by_workflow(self):
        response = self.client.get(
            "/api/v1/procurement/direct-opportunities/",
            {"workflow_view": "selected"},
        )
        self.assertEqual(response.status_code, 200)
        snapshot = performance_assurance_snapshot(compact=True)
        key = "procurement.ui.direct.list.selected"
        self.assertIn(key, snapshot["metrics"])
        self.assertEqual(snapshot["metrics"][key]["risk"], "hot_path")
        self.assertGreaterEqual(snapshot["metrics"][key]["sample_count"], 1)
