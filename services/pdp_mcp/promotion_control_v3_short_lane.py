"""Short-critical-lane policy instrumentation for Promotion Control V3.

DEC-051 keeps the shared promotion lease only for exact deployment, immediate
health/smoke, PRE-MERGE and exact-head merge. Long SLA/soak/natural-run
observation is post-merge Extended Acceptance and must not be mistaken for a
reason to keep the promotion lane indefinitely.

This module deliberately does not auto-release an unmerged deployed ticket:
doing so could allow a later candidate based on an older main to replace the
unmerged runtime source tree. Instead it makes the short-lane contract explicit
and surfaces a bounded hold violation so governed agents resolve the ticket by
exact initial health + PRE-MERGE/merge (or fail closed) rather than waiting for
long-duration operational evidence.
"""

from __future__ import annotations

import os
from typing import Any

import promotion_control_v3 as promotion

REVISION = "pdp-one.parallel-promotion-control.v3.1-short-critical-lane"
IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS = max(
    60,
    min(3600, int(os.getenv("PDP_PROMOTION_IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS", "900"))),
)

_original_status_snapshot = promotion.status_snapshot


def status_snapshot() -> dict[str, Any]:
    value = _original_status_snapshot()
    value["revision"] = REVISION
    value["lane_model"] = "short_critical"
    value["promotion_lane_scope"] = "exact_deploy_immediate_health_pre_merge_merge"
    value["extended_acceptance_blocks_lane"] = False
    value["extended_acceptance_phase"] = "post_merge"
    value["exact_source_cumulative"] = True
    value["immediate_acceptance_budget_seconds"] = IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS

    active = value.get("active_ticket")
    value["lane_hold_violation"] = False
    if isinstance(active, dict) and str(active.get("state", "")) == "acceptance":
        raw = promotion._active_ticket_unlocked()
        completed = promotion._parse_time((raw or {}).get("deployment_completed_at")) if raw else None
        if completed:
            age = max(0, int((promotion._now() - completed).total_seconds()))
            value["immediate_acceptance_age_seconds"] = age
            if age > IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS:
                value["lane_hold_violation"] = True
                value["lane_required_action"] = (
                    "run_exact_initial_health_then_pre_merge_merge_or_fail_closed; "
                    "do_not_wait_for_extended_sla_soak_in_lane"
                )
    return value


promotion.status_snapshot = status_snapshot
promotion.SHORT_CRITICAL_LANE_REVISION = REVISION
promotion.IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS = IMMEDIATE_ACCEPTANCE_BUDGET_SECONDS
