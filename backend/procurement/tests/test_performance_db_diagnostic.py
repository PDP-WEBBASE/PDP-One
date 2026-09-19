from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from procurement.performance_db_diagnostic import collect_inquiry_recommended_db_diagnostic


class InquiryRecommendedDbDiagnosticTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="db-diagnostic-user",
            password="test-pass-123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_diagnostic_is_bounded_sanitized_and_cached(self):
        first = collect_inquiry_recommended_db_diagnostic(self.user, force=True)
        self.assertEqual(first["schema"], "pdp-one.inquiry-recommended-db-diagnostic.v1")
        self.assertTrue(first["read_only"])
        self.assertFalse(first["stress_test"])
        self.assertFalse(first["explain_analyze_used"])
        self.assertFalse(first["sql_text_recorded"])
        self.assertFalse(first["sql_params_recorded"])
        self.assertFalse(first["business_payload_recorded"])
        self.assertEqual(first["page_size"], 50)
        self.assertIn("query_sample", first)
        self.assertIn("plan", first)
        self.assertIn("postgres", first)
        self.assertIn("analysis", first)
        self.assertNotIn("sql", first["query_sample"])
        self.assertNotIn("params", first["query_sample"])

        second = collect_inquiry_recommended_db_diagnostic(self.user)
        self.assertTrue(second["cache_hit"])

    def test_system_status_db_diagnostic_is_explicitly_gated(self):
        normal = self.client.get("/api/v1/system-status/")
        self.assertEqual(normal.status_code, 200)
        self.assertIsNone(normal.json()["performance_db_diagnostic"])

        probed = self.client.get(
            "/api/v1/system-status/",
            {"performance_db_diagnostic": "1"},
        )
        self.assertEqual(probed.status_code, 200)
        payload = probed.json()["performance_db_diagnostic"]
        self.assertEqual(payload["schema"], "pdp-one.inquiry-recommended-db-diagnostic.v1")
        self.assertFalse(payload["explain_analyze_used"])
