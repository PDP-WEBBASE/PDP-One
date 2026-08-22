from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from procurement.models_extraction import ExtractionRun
from procurement.tasks import (
    _known_boundary_can_stop,
    _next_known_page_count,
    _page_proves_recent_overlap_boundary,
    _setad_recent_overlap_cutoff,
)


class SetadTenderRecentOverlapPolicyTests(SimpleTestCase):
    def _connector(self, key="setad_tenders", overlap_days=2):
        return SimpleNamespace(key=key, overlap_days=overlap_days)

    def _run(self, mode=ExtractionRun.Mode.INCREMENTAL):
        return SimpleNamespace(mode=mode)

    @mock.patch("procurement.tasks.timezone.localdate", return_value=date(2026, 8, 22))
    def test_incremental_setad_tender_uses_connector_overlap_days(self, localdate):
        cutoff = _setad_recent_overlap_cutoff(
            self._run(),
            self._connector(overlap_days=2),
            first_run=False,
        )

        self.assertEqual(cutoff, date(2026, 8, 20))
        localdate.assert_called_once_with()

    def test_non_setad_or_first_run_does_not_require_recent_overlap_floor(self):
        self.assertIsNone(
            _setad_recent_overlap_cutoff(
                self._run(),
                self._connector(key="parsnamad_inquiries"),
                first_run=False,
            )
        )
        self.assertIsNone(
            _setad_recent_overlap_cutoff(
                self._run(),
                self._connector(),
                first_run=True,
            )
        )

    def test_page_must_be_fully_dated_and_older_than_cutoff_to_prove_floor(self):
        cutoff = date(2026, 8, 20)

        self.assertFalse(
            _page_proves_recent_overlap_boundary(
                [date(2026, 8, 22), date(2026, 8, 21)],
                cutoff,
            )
        )
        self.assertFalse(
            _page_proves_recent_overlap_boundary(
                [date(2026, 8, 19), None],
                cutoff,
            )
        )
        self.assertTrue(
            _page_proves_recent_overlap_boundary(
                [date(2026, 8, 19), date(2026, 8, 18)],
                cutoff,
            )
        )

    def test_two_known_pages_inside_overlap_do_not_stop_setad(self):
        self.assertFalse(
            _known_boundary_can_stop(
                connector_key="setad_tenders",
                page_number=2,
                consecutive_known_pages=2,
                recent_overlap_required=True,
                recent_overlap_satisfied=False,
            )
        )
        self.assertTrue(
            _known_boundary_can_stop(
                connector_key="setad_tenders",
                page_number=3,
                consecutive_known_pages=3,
                recent_overlap_required=True,
                recent_overlap_satisfied=True,
            )
        )

    def test_update_resets_known_page_sequence_before_overlap_stop(self):
        known = _next_known_page_count(
            1,
            {"new": 0, "updated": 0, "duplicate": 30, "failed": 0},
        )
        self.assertEqual(known, 2)

        after_update = _next_known_page_count(
            known,
            {"new": 0, "updated": 1, "duplicate": 29, "failed": 0},
        )
        self.assertEqual(after_update, 0)

    def test_existing_hezareh_page_three_floor_and_other_connectors_are_preserved(self):
        self.assertFalse(
            _known_boundary_can_stop(
                connector_key="hezareh_inquiries",
                page_number=2,
                consecutive_known_pages=2,
                recent_overlap_required=False,
                recent_overlap_satisfied=True,
            )
        )
        self.assertTrue(
            _known_boundary_can_stop(
                connector_key="hezareh_inquiries",
                page_number=3,
                consecutive_known_pages=3,
                recent_overlap_required=False,
                recent_overlap_satisfied=True,
            )
        )
        self.assertTrue(
            _known_boundary_can_stop(
                connector_key="parsnamad_inquiries",
                page_number=2,
                consecutive_known_pages=2,
                recent_overlap_required=False,
                recent_overlap_satisfied=True,
            )
        )
