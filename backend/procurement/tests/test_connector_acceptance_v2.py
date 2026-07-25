from django.test import SimpleTestCase

from procurement.tasks_connector_acceptance_v2 import (
    _compact_connector,
    _requested_detail_probe_limit,
    _totals,
)


class ConnectorAcceptanceV2Tests(SimpleTestCase):
    def test_requested_detail_probe_limit_can_disable_probes(self):
        self.assertEqual(_requested_detail_probe_limit({"detail_probe_limit": 0}), 0)
        self.assertEqual(_requested_detail_probe_limit({"detail_probe_limit": 8}), 2)
        self.assertEqual(_requested_detail_probe_limit({}), 2)

    def test_compact_connector_keeps_duplicate_and_probe_evidence(self):
        errors = [
            {"category": "parse", "safe_message": f"error-{index}"}
            for index in range(12)
        ]
        result = _compact_connector(
            {
                "key": "parsnamad_inquiries",
                "tested": True,
                "acceptance": "warning",
                "run_status": "succeeded_with_warnings",
                "records_seen": 20,
                "cross_source_duplicate_links": 3,
                "normalized_record_count": 20,
                "error_count": len(errors),
                "errors": errors,
                "detail_probes": [{"status": "warning"}],
            }
        )
        self.assertEqual(result["cross_source_duplicate_links"], 3)
        self.assertEqual(result["normalized_record_count"], 20)
        self.assertEqual(len(result["errors"]), 10)
        self.assertEqual(result["errors_truncated"], 2)
        self.assertEqual(result["detail_probes"][0]["status"], "warning")

    def test_totals_include_cross_source_duplicates_and_detail_probes(self):
        totals = _totals(
            [
                {
                    "tested": True,
                    "acceptance": "passed",
                    "pages_processed": 2,
                    "records_seen": 10,
                    "records_new": 8,
                    "records_updated": 2,
                    "records_duplicate": 0,
                    "cross_source_duplicate_links": 1,
                    "records_failed": 0,
                    "error_count": 0,
                    "detail_probes": [{"status": "passed"}, {"status": "warning"}],
                },
                {
                    "tested": False,
                    "acceptance": "disabled",
                },
            ]
        )
        self.assertEqual(totals["tested_connectors"], 1)
        self.assertEqual(totals["cross_source_duplicate_links"], 1)
        self.assertEqual(totals["detail_probes"], 2)
        self.assertEqual(totals["detail_probe_passed"], 1)
        self.assertEqual(totals["disabled"], 1)
