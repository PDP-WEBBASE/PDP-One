from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import deployment_coordinator as coordinator
import deployment_queue
import promotion_control_v3 as promotion
import server as reconciliation


SHA_A = "a" * 40
SHA_B = "b" * 40
DEPLOYMENT_CLIENT = "11111111-1111-4111-8111-111111111111"
DEPLOYMENT_AGENT = "22222222-2222-4222-8222-222222222222"
HEALTH_CLIENT = "33333333-3333-4333-8333-333333333333"
HEALTH_AGENT = "44444444-4444-4444-8444-444444444444"
TICKET_ID = "55555555-5555-4555-8555-555555555555"
DEPLOYMENT_ID = "v3-reconciliation-test-r1"


class CoordinatorV3ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        queue_root = root / "queue"
        coordinator_root = queue_root / "coordinator"
        self._old = {
            "queue_root": deployment_queue.QUEUE_ROOT,
            "reserve": deployment_queue.RESERVE_PATH,
            "signing": deployment_queue.SIGNING_KEY,
            "root": coordinator.ROOT,
            "workstreams": coordinator.WORKSTREAMS,
            "pending": coordinator.PENDING,
            "history": coordinator.HISTORY,
            "live": coordinator.LIVE_TEST_LEASES,
            "lease": coordinator.PROMOTION_LEASE,
            "lock": coordinator.MUTATION_LOCK,
            "promotion_ensure_started": promotion.ensure_started,
        }
        deployment_queue.QUEUE_ROOT = queue_root
        deployment_queue.RESERVE_PATH = queue_root / ".queue-emergency-reserve"
        deployment_queue.SIGNING_KEY = "x" * 64
        coordinator.ROOT = coordinator_root
        coordinator.WORKSTREAMS = coordinator_root / "workstreams"
        coordinator.PENDING = coordinator_root / "pending"
        coordinator.HISTORY = coordinator_root / "history"
        coordinator.LIVE_TEST_LEASES = coordinator_root / "live-test-leases"
        coordinator.PROMOTION_LEASE = coordinator_root / "promotion-lease.json"
        coordinator.MUTATION_LOCK = coordinator_root / ".mutation-lock"
        promotion.configure_queue_root(queue_root)
        promotion.ensure_started = lambda: None
        for name in ("incoming", "processing", "responses"):
            (queue_root / name).mkdir(parents=True, exist_ok=True)
        self.item = coordinator.register_workstream(
            workstream_id="v3-reconcile",
            branch="fix/v3-reconcile",
            changed_paths=["services/pdp_mcp/server.py"],
            surfaces=["candidate-acceptance"],
            commit_sha=SHA_A,
            pull_request=210,
            origin_chat_ref="test-v3-reconcile",
            components=["pdp_mcp"],
            runtime_resources=["pdp-mcp"],
            base_sha=SHA_B,
            current_main_sha=SHA_B,
            required_evidence=[],
        )
        self.candidate_id = self.item["current_candidate_id"]

    def tearDown(self) -> None:
        deployment_queue.QUEUE_ROOT = self._old["queue_root"]
        deployment_queue.RESERVE_PATH = self._old["reserve"]
        deployment_queue.SIGNING_KEY = self._old["signing"]
        coordinator.ROOT = self._old["root"]
        coordinator.WORKSTREAMS = self._old["workstreams"]
        coordinator.PENDING = self._old["pending"]
        coordinator.HISTORY = self._old["history"]
        coordinator.LIVE_TEST_LEASES = self._old["live"]
        coordinator.PROMOTION_LEASE = self._old["lease"]
        coordinator.MUTATION_LOCK = self._old["lock"]
        promotion.ensure_started = self._old["promotion_ensure_started"]
        promotion.configure_queue_root(deployment_queue.QUEUE_ROOT)
        self._temporary.cleanup()

    def _write_v3_evidence(self, *, health_ticket_id: str = TICKET_ID, runtime_accepted: bool = True) -> None:
        deployment_record = {
            "schema": "pdp-one.promotion-request.v3",
            "client_request_id": DEPLOYMENT_CLIENT,
            "agent_request_id": DEPLOYMENT_AGENT,
            "action": "promote_exact_candidate",
            "commit_sha": SHA_A,
            "deployment_id": DEPLOYMENT_ID,
            "ticket_id": TICKET_ID,
            "state": "pre_merge",
            "terminal_status": "succeeded",
        }
        health_record = {
            "schema": "pdp-one.promotion-health-request.v3",
            "client_request_id": HEALTH_CLIENT,
            "agent_request_id": HEALTH_AGENT,
            "action": "check_deployment_health",
            "commit_sha": SHA_A,
            "deployment_id": DEPLOYMENT_ID,
            "ticket_id": health_ticket_id,
            "state": "succeeded",
            "terminal_status": "succeeded",
        }
        ticket = {
            "schema": "pdp-one.promotion-ticket.v3",
            "ticket_id": TICKET_ID,
            "client_request_id": DEPLOYMENT_CLIENT,
            "agent_request_id": DEPLOYMENT_AGENT,
            "health_client_request_id": HEALTH_CLIENT,
            "health_agent_request_id": HEALTH_AGENT,
            "commit_sha": SHA_A,
            "deployment_id": DEPLOYMENT_ID,
            "state": "pre_merge",
            "runtime_accepted": runtime_accepted,
        }
        promotion._atomic_json(promotion.REQUESTS / f"{DEPLOYMENT_CLIENT}.json", deployment_record)
        promotion._atomic_json(promotion.REQUESTS / f"{HEALTH_CLIENT}.json", health_record)
        promotion._atomic_json(promotion.ACTIVE, ticket)

    def test_client_request_reconciles_exact_v3_evidence_and_reaches_pre_merge(self) -> None:
        self._write_v3_evidence()
        accepted = reconciliation._record_candidate_acceptance_with_v3(
            "v3-reconcile", self.candidate_id, SHA_A, DEPLOYMENT_CLIENT, DEPLOYMENT_ID, HEALTH_CLIENT, "healthy"
        )
        self.assertEqual(accepted["state"], "pre_merge")
        self.assertEqual(accepted["acceptance"]["deployment_request_id"], DEPLOYMENT_CLIENT)
        history = json.loads((coordinator.HISTORY / f"{DEPLOYMENT_CLIENT}.json").read_text(encoding="utf-8"))
        self.assertEqual(history["evidence_source"], "promotion-v3")
        self.assertEqual(history["promotion_ticket_id"], TICKET_ID)

    def test_agent_request_is_canonicalized_to_v3_client_request(self) -> None:
        self._write_v3_evidence()
        accepted = reconciliation._record_candidate_acceptance_with_v3(
            "v3-reconcile", self.candidate_id, SHA_A, DEPLOYMENT_AGENT, DEPLOYMENT_ID, HEALTH_AGENT, "healthy"
        )
        self.assertEqual(accepted["acceptance"]["deployment_request_id"], DEPLOYMENT_CLIENT)
        self.assertEqual(accepted["acceptance"]["health_request_id"], HEALTH_CLIENT)

    def test_mismatched_health_ticket_fails_closed_without_history_synthesis(self) -> None:
        self._write_v3_evidence(health_ticket_id="66666666-6666-4666-8666-666666666666")
        with self.assertRaisesRegex(ValueError, "do not share one exact ticket"):
            reconciliation._record_candidate_acceptance_with_v3(
                "v3-reconcile", self.candidate_id, SHA_A, DEPLOYMENT_CLIENT, DEPLOYMENT_ID, HEALTH_CLIENT, "healthy"
            )
        self.assertFalse((coordinator.HISTORY / f"{DEPLOYMENT_CLIENT}.json").exists())

    def test_non_accepted_v3_ticket_fails_closed(self) -> None:
        self._write_v3_evidence(runtime_accepted=False)
        with self.assertRaisesRegex(ValueError, "not runtime accepted"):
            reconciliation._record_candidate_acceptance_with_v3(
                "v3-reconcile", self.candidate_id, SHA_A, DEPLOYMENT_CLIENT, DEPLOYMENT_ID, HEALTH_CLIENT, "healthy"
            )
        self.assertFalse((coordinator.HISTORY / f"{DEPLOYMENT_CLIENT}.json").exists())


if __name__ == "__main__":
    unittest.main()
