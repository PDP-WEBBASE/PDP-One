from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

import promotion_control_v3 as promotion
import promotion_control_v3_short_lane as short_lane


class PromotionControlShortLaneTests(unittest.TestCase):
    def test_status_declares_non_blocking_post_merge_extended_acceptance(self) -> None:
        base = {
            "revision": "pdp-one.parallel-promotion-control.v3",
            "active_ticket": None,
            "single_final_promotion_lane": True,
        }
        with mock.patch.object(short_lane, "_original_status_snapshot", return_value=base):
            value = short_lane.status_snapshot()
        self.assertEqual(value["revision"], short_lane.REVISION)
        self.assertEqual(value["lane_model"], "short_critical")
        self.assertFalse(value["extended_acceptance_blocks_lane"])
        self.assertEqual(value["extended_acceptance_phase"], "post_merge")
        self.assertTrue(value["exact_source_cumulative"])
        self.assertFalse(value["lane_hold_violation"])

    def test_old_acceptance_surfaces_lane_hold_violation_without_auto_release(self) -> None:
        completed = promotion._now() - timedelta(seconds=short_lane.IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS + 5)
        base = {
            "active_ticket": {"state": "acceptance", "ticket_id": "ticket-a"},
            "single_final_promotion_lane": True,
        }
        raw = {"state": "acceptance", "ticket_id": "ticket-a", "deployment_completed_at": promotion._iso(completed)}
        with mock.patch.object(short_lane, "_original_status_snapshot", return_value=base), mock.patch.object(
            promotion, "_active_ticket_unlocked", return_value=raw
        ):
            value = short_lane.status_snapshot()
        self.assertTrue(value["lane_hold_violation"])
        self.assertGreater(value["immediate_acceptance_age_seconds"], short_lane.IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS)
        self.assertIn("pre_merge_merge_or_fail_closed", value["lane_required_action"])
        # The instrumentation never mutates or releases the active ticket.
        self.assertEqual(raw["state"], "acceptance")


if __name__ == "__main__":
    unittest.main()
