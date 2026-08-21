from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

import deployment_coordinator as coordinator
import deployment_queue


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class DeploymentCoordinatorV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        queue_root = root / "queue"
        coordinator_root = queue_root / "coordinator"

        self._old_values = {
            "queue_root": deployment_queue.QUEUE_ROOT,
            "reserve_path": deployment_queue.RESERVE_PATH,
            "signing_key": deployment_queue.SIGNING_KEY,
            "root": coordinator.ROOT,
            "workstreams": coordinator.WORKSTREAMS,
            "pending": coordinator.PENDING,
            "history": coordinator.HISTORY,
            "live_test_leases": coordinator.LIVE_TEST_LEASES,
            "promotion_lease": coordinator.PROMOTION_LEASE,
            "mutation_lock": coordinator.MUTATION_LOCK,
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

        for name in ("incoming", "processing", "responses"):
            (queue_root / name).mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        deployment_queue.QUEUE_ROOT = self._old_values["queue_root"]
        deployment_queue.RESERVE_PATH = self._old_values["reserve_path"]
        deployment_queue.SIGNING_KEY = self._old_values["signing_key"]
        coordinator.ROOT = self._old_values["root"]
        coordinator.WORKSTREAMS = self._old_values["workstreams"]
        coordinator.PENDING = self._old_values["pending"]
        coordinator.HISTORY = self._old_values["history"]
        coordinator.LIVE_TEST_LEASES = self._old_values["live_test_leases"]
        coordinator.PROMOTION_LEASE = self._old_values["promotion_lease"]
        coordinator.MUTATION_LOCK = self._old_values["mutation_lock"]
        self._temporary.cleanup()

    def _register(self, workstream_id: str, head: str = SHA_A, path: str = "services/pdp_mcp/deployment_coordinator.py") -> dict:
        return coordinator.register_workstream(
            workstream_id=workstream_id,
            branch=f"feat/{workstream_id}",
            changed_paths=[path],
            surfaces=["mcp-coordinator"],
            commit_sha=head,
            pull_request=200,
            origin_chat_ref=f"chat-{workstream_id}",
            components=["mcp"],
            runtime_resources=["mcp-runtime"],
            base_sha=SHA_B,
            current_main_sha=SHA_B,
            required_evidence=["public-boundary", "verify"],
        )

    def _ready_candidate(self, workstream_id: str) -> tuple[dict, str]:
        item = self._register(workstream_id)
        candidate_id = item["current_candidate_id"]
        coordinator.record_candidate_evidence(
            workstream_id,
            candidate_id,
            "public-boundary",
            "boundary-run-1",
            "success",
            SHA_A,
        )
        candidate = coordinator.record_candidate_evidence(
            workstream_id,
            candidate_id,
            "verify",
            "ci-run-1",
            "success",
            SHA_A,
        )
        self.assertEqual(candidate["evidence_state"], "ready")
        return item, candidate_id

    def test_new_head_stales_previous_candidate_and_wrong_head_evidence_is_rejected(self) -> None:
        _item, first_candidate_id = self._ready_candidate("evidence-lineage")
        second = coordinator.register_candidate(
            "evidence-lineage",
            SHA_C,
            SHA_B,
            pull_request=200,
            current_main_sha=SHA_B,
            required_evidence=["public-boundary", "verify"],
        )
        refreshed = json.loads((coordinator.WORKSTREAMS / "evidence-lineage.json").read_text(encoding="utf-8"))
        self.assertEqual(refreshed["candidates"][first_candidate_id]["state"], "stale")
        self.assertEqual(refreshed["candidates"][first_candidate_id]["evidence_state"], "stale")
        self.assertEqual(refreshed["current_candidate_id"], second["candidate_id"])

        with self.assertRaisesRegex(ValueError, "does not match"):
            coordinator.record_candidate_evidence(
                "evidence-lineage",
                second["candidate_id"],
                "verify",
                "ci-run-old-head",
                "success",
                SHA_A,
            )

    def test_atomic_registration_exposes_same_scope_conflict_to_parallel_workstreams(self) -> None:
        errors: list[Exception] = []

        def register(workstream_id: str) -> None:
            try:
                self._register(workstream_id)
            except Exception as exc:  # pragma: no cover - diagnostic path
                errors.append(exc)

        first = threading.Thread(target=register, args=("parallel-a",))
        second = threading.Thread(target=register, args=("parallel-b",))
        first.start()
        second.start()
        first.join()
        second.join()
        self.assertEqual(errors, [])

        status = coordinator.coordinator_status()
        by_id = {item["workstream_id"]: item for item in status["workstreams"]}
        self.assertTrue(by_id["parallel-a"]["conflicts"])
        self.assertTrue(by_id["parallel-b"]["conflicts"])
        shared = by_id["parallel-a"]["conflicts"][0]
        self.assertIn("services/pdp_mcp/deployment_coordinator.py", shared["shared_paths"])
        self.assertIn("mcp", shared["shared_components"])

    def test_promotion_rejects_old_base_and_accepts_exact_current_main(self) -> None:
        _item, candidate_id = self._ready_candidate("promotion-base")
        with self.assertRaisesRegex(ValueError, "not integrated"):
            coordinator.reserve_promotion("promotion-base", candidate_id, SHA_A, SHA_C)

        lease = coordinator.reserve_promotion("promotion-base", candidate_id, SHA_A, SHA_B)
        self.assertEqual(lease["head_sha"], SHA_A)
        self.assertEqual(lease["current_main_sha"], SHA_B)

    def test_successful_deployment_stays_in_acceptance_until_exact_health_and_merge(self) -> None:
        _item, candidate_id = self._ready_candidate("acceptance-flow")
        coordinator.reserve_promotion("acceptance-flow", candidate_id, SHA_A, SHA_B)
        deployment = coordinator.queue_exact_deployment(
            workstream_id="acceptance-flow",
            commit_sha=SHA_A,
            deployment_id="promotion-test-r1",
            preview_id="preview-test-r1",
            candidate_id=candidate_id,
            current_main_sha=SHA_B,
        )
        request_id = deployment["request_id"]
        (deployment_queue.QUEUE_ROOT / "incoming" / f"{request_id}.json").unlink(missing_ok=True)
        (deployment_queue.QUEUE_ROOT / "responses" / f"{request_id}.json").write_text(
            json.dumps({"status": "succeeded"}),
            encoding="utf-8",
        )

        status = coordinator.coordinator_status()
        workstream = next(item for item in status["workstreams"] if item["workstream_id"] == "acceptance-flow")
        self.assertEqual(workstream["state"], "acceptance")
        self.assertIsNotNone(status["promotion_lease"])
        self.assertFalse(workstream["lock_expired"])

        health_request_id = "00000000-0000-0000-0000-000000000001"
        accepted = coordinator.record_candidate_acceptance(
            "acceptance-flow",
            candidate_id,
            SHA_A,
            request_id,
            "promotion-test-r1",
            health_request_id,
            "healthy",
        )
        self.assertEqual(accepted["state"], "pre_merge")
        completed = coordinator.complete_workstream(
            "acceptance-flow",
            "merged",
            candidate_id=candidate_id,
            head_sha=SHA_A,
            merge_sha=SHA_C,
        )
        self.assertEqual(completed["state"], "merged")
        self.assertFalse(coordinator.PROMOTION_LEASE.exists())

    def test_cross_chat_handoff_requires_explicit_owner_request(self) -> None:
        self._register("handoff")
        with self.assertRaisesRegex(ValueError, "explicit owner-requested"):
            coordinator.record_workstream_handoff("handoff", "chat-a", "chat-b", False)

        item = coordinator.record_workstream_handoff("handoff", "chat-a", "chat-b", True)
        self.assertEqual(item["origin_chat_ref"], "chat-handoff")
        self.assertEqual(item["continuation_chat_ref"], "chat-b")
        self.assertFalse(item["automatic_cross_chat_takeover"])
        self.assertEqual(item["handoff_history"][-1]["to_chat_ref"], "chat-b")

    def test_live_test_lease_prevents_same_source_acceptance_collision(self) -> None:
        _first, first_candidate = self._ready_candidate("live-a")
        second = coordinator.register_workstream(
            workstream_id="live-b",
            branch="feat/live-b",
            changed_paths=["backend/procurement/connectors/parsnamad.py"],
            surfaces=["parsnamad-parser"],
            commit_sha=SHA_C,
            pull_request=201,
            origin_chat_ref="chat-live-b",
            components=["backend"],
            runtime_resources=["backend-runtime"],
            live_test_scopes=["parsnamad"],
            base_sha=SHA_B,
            current_main_sha=SHA_B,
            required_evidence=[],
        )
        second_candidate = second["current_candidate_id"]
        coordinator.acquire_live_test_lease("parsnamad", "live-a", first_candidate)
        with self.assertRaisesRegex(ValueError, "Another workstream"):
            coordinator.acquire_live_test_lease("parsnamad", "live-b", second_candidate)
        released = coordinator.release_live_test_lease("parsnamad", "live-a")
        self.assertTrue(released["released"])


if __name__ == "__main__":
    unittest.main()
