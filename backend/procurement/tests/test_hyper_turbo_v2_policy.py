from django.test import SimpleTestCase

from procurement.analysis_throughput import (
    MIN_OPERATIONAL_SLA_PER_HOUR,
    PER_LANE_HOURLY_CEILING,
    SAFE_PACKAGE_SIZE,
    adaptive_throughput_policy,
)


class HyperTurboV2PolicyTests(SimpleTestCase):
    def test_high_backlog_keeps_eight_lanes_and_1000_hourly_window(self):
        policy = adaptive_throughput_policy(25000)

        self.assertEqual(policy["mode"], "hyper_turbo_v2")
        self.assertEqual(policy["desired_lanes"], 8)
        self.assertEqual(policy["claim_window_target_per_lane"], 1000)
        self.assertEqual(policy["per_lane_hourly_ceiling"], 1000)
        self.assertEqual(policy["micro_batch_size"], 50)
        self.assertEqual(policy["max_packages_per_lane"], 20)
        self.assertEqual(policy["planned_capacity_per_hour"], 8000)
        self.assertEqual(policy["target_per_hour"], 8000)

    def test_medium_backlog_remains_aggressive_and_keeps_eight_lanes(self):
        policy = adaptive_throughput_policy(7000)

        self.assertEqual(policy["desired_lanes"], 8)
        self.assertEqual(policy["claim_window_target_per_lane"], 750)
        self.assertEqual(policy["max_packages_per_lane"], 15)
        self.assertEqual(policy["planned_capacity_per_hour"], 6000)

    def test_2000_to_5000_backlog_keeps_eight_lanes_with_500_window(self):
        policy = adaptive_throughput_policy(3000)

        self.assertEqual(policy["desired_lanes"], 8)
        self.assertEqual(policy["claim_window_target_per_lane"], 500)
        self.assertEqual(policy["target_per_hour"], 4000)
        self.assertEqual(policy["planned_capacity_per_hour"], 4000)

    def test_small_but_material_backlog_does_not_collapse_to_one_lane(self):
        policy = adaptive_throughput_policy(900)

        self.assertEqual(policy["desired_lanes"], 8)
        self.assertEqual(policy["claim_window_target_per_lane"], 500)
        self.assertEqual(policy["target_per_hour"], MIN_OPERATIONAL_SLA_PER_HOUR)

    def test_near_empty_queue_reduces_lanes_without_overclaim_assumption(self):
        policy = adaptive_throughput_policy(120)

        self.assertEqual(policy["desired_lanes"], 3)
        self.assertEqual(policy["claim_window_target_per_lane"], 120)
        self.assertEqual(policy["target_per_hour"], 120)

    def test_backpressure_reduces_cycles_not_semantic_batch_size(self):
        policy = adaptive_throughput_policy(
            25000,
            recent_completed=100,
            recent_lease_expired=50,
        )

        self.assertEqual(policy["backpressure"], "degraded")
        self.assertEqual(policy["micro_batch_size"], SAFE_PACKAGE_SIZE)
        self.assertEqual(policy["per_lane_hourly_ceiling"], PER_LANE_HOURLY_CEILING)
        self.assertEqual(policy["max_packages_per_lane"], 10)
        self.assertEqual(policy["planned_capacity_per_hour"], 4000)
