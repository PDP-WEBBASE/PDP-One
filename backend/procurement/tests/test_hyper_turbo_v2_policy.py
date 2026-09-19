from django.test import SimpleTestCase

from procurement.analysis_run_adaptive import GLOBAL_ACTIVE_CLAIM_CAP, SAFE_CLAIM_LIMIT
from procurement.analysis_throughput import (
    DESIGN_CAPACITY_PER_HOUR,
    MAX_ANALYSIS_LANES,
    PER_LANE_HOURLY_CEILING,
    SAFE_PACKAGE_SIZE,
    TARGET_SLA_PER_HOUR,
    adaptive_throughput_policy,
)


class HyperTurboV3PolicyTests(SimpleTestCase):
    def test_high_backlog_targets_30k_with_40k_design_capacity(self):
        policy = adaptive_throughput_policy(50000)

        self.assertEqual(policy["mode"], "hyper_turbo_v3")
        self.assertEqual(policy["desired_lanes"], 40)
        self.assertEqual(policy["claim_reservation_size"], 250)
        self.assertEqual(policy["claim_window_target_per_lane"], 1000)
        self.assertEqual(policy["per_lane_hourly_ceiling"], 1000)
        self.assertEqual(policy["micro_batch_size"], 50)
        self.assertEqual(policy["max_packages_per_lane"], 20)
        self.assertEqual(policy["planned_capacity_per_hour"], 40000)
        self.assertEqual(policy["target_per_hour"], 30000)
        self.assertEqual(policy["rolling_sla_target_per_hour"], TARGET_SLA_PER_HOUR)
        self.assertEqual(policy["design_capacity_per_hour"], DESIGN_CAPACITY_PER_HOUR)
        self.assertEqual(policy["logical_lanes_per_executor"], 5)
        self.assertEqual(policy["scheduled_analysis_executors"], 8)

    def test_fixed_claim_reservation_and_global_cap_match_40_logical_lanes(self):
        self.assertEqual(SAFE_CLAIM_LIMIT, 250)
        self.assertEqual(MAX_ANALYSIS_LANES, 40)
        self.assertEqual(GLOBAL_ACTIVE_CLAIM_CAP, 10000)
        self.assertEqual(GLOBAL_ACTIVE_CLAIM_CAP, MAX_ANALYSIS_LANES * SAFE_CLAIM_LIMIT)

    def test_backlog_below_30k_drains_without_fabricating_sla_work(self):
        policy = adaptive_throughput_policy(25000)

        self.assertEqual(policy["mode"], "turbo_v3")
        self.assertEqual(policy["desired_lanes"], 40)
        self.assertEqual(policy["target_per_hour"], 25000)
        self.assertEqual(policy["sla_state"], "draining_small_backlog")

    def test_medium_backlog_scales_logical_lanes_by_250_item_reservations(self):
        policy = adaptive_throughput_policy(7000)

        self.assertEqual(policy["desired_lanes"], 28)
        self.assertEqual(policy["claim_window_target_per_lane"], 750)
        self.assertEqual(policy["max_packages_per_lane"], 15)
        self.assertEqual(policy["target_per_hour"], 7000)

    def test_near_empty_queue_reduces_lanes_without_overclaim(self):
        policy = adaptive_throughput_policy(120)

        self.assertEqual(policy["desired_lanes"], 1)
        self.assertEqual(policy["claim_window_target_per_lane"], 120)
        self.assertEqual(policy["target_per_hour"], 120)

    def test_backpressure_reduces_cycles_not_semantic_batch_or_reservation_size(self):
        policy = adaptive_throughput_policy(
            50000,
            recent_completed=100,
            recent_lease_expired=50,
        )

        self.assertEqual(policy["backpressure"], "degraded")
        self.assertEqual(policy["micro_batch_size"], SAFE_PACKAGE_SIZE)
        self.assertEqual(policy["claim_reservation_size"], SAFE_CLAIM_LIMIT)
        self.assertEqual(policy["per_lane_hourly_ceiling"], PER_LANE_HOURLY_CEILING)
        self.assertEqual(policy["max_packages_per_lane"], 10)
        self.assertEqual(policy["planned_capacity_per_hour"], 20000)

    def test_rolling_sla_states_use_valid_import_rate(self):
        self.assertEqual(adaptive_throughput_policy(50000, recent_completed=34000)["sla_state"], "green")
        self.assertEqual(adaptive_throughput_policy(50000, recent_completed=30500)["sla_state"], "guarded")
        self.assertEqual(adaptive_throughput_policy(50000, recent_completed=25000)["sla_state"], "recovery")
        self.assertEqual(adaptive_throughput_policy(50000, recent_completed=10000)["sla_state"], "critical")
