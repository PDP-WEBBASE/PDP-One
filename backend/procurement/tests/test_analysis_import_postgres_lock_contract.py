from __future__ import annotations

import inspect

from django.test import SimpleTestCase

from procurement.analysis_run_service import finalize_run_if_exhausted, import_result_records


class ProcurementImportPostgresLockContractTests(SimpleTestCase):
    def test_locked_run_queries_do_not_join_nullable_analysis_request(self):
        source = inspect.getsource(import_result_records) + inspect.getsource(finalize_run_if_exhausted)
        self.assertNotIn(
            '.select_related("context_snapshot", "analysis_request")',
            source,
        )
        self.assertNotIn('.select_related("analysis_request")', source)
