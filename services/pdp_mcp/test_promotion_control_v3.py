from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import deployment_queue
import promotion_control_v3 as promotion


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class PromotionControlV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        queue = root / "queue"
        reports = root / "reports"
        promo = queue / "promotion-v3"

        self.old = {
            "queue_root": deployment_queue.QUEUE_ROOT,
            "report_root": deployment_queue.REPORT_ROOT,
            "reserve": deployment_queue.RESERVE_PATH,
            "key": deployment_queue.SIGNING_KEY,
            "promotion_import": deployment_queue._promotion_v3,
            "root": promotion.ROOT,
            "ready": promotion.READY,
            "requests": promotion.REQUESTS,
            "history": promotion.HISTORY,
            "attestations": promotion.ATTESTATIONS,
            "active": promotion.ACTIVE,
            "lock": promotion.LOCK,
            "shared": promotion.SHARED_PROMOTION_LEASE,
            "started": promotion._started,
            "background_error": promotion._last_background_error,
        }

        deployment_queue.QUEUE_ROOT = queue
        deployment_queue.REPORT_ROOT = reports
        deployment_queue.RESERVE_PATH = queue / ".queue-emergency-reserve"
        deployment_queue.SIGNING_KEY = "x" * 64
        deployment_queue._promotion_v3 = lambda: promotion

        promotion.ROOT = promo
        promotion.READY = promo / "ready"
        promotion.REQUESTS = promo / "requests"
        promotion.HISTORY = promo / "history"
        promotion.ATTESTATIONS = promo / "attestations"
        promotion.ACTIVE = promo / "active-ticket.json"
        promotion.LOCK = promo / ".mutation-lock"
        promotion.SHARED_PROMOTION_LEASE = queue / "coordinator" / "promotion-lease.json"
        promotion._started = True  # deterministic tests: no background thread
        promotion._last_background_error = None

        for path in (
            queue / "incoming",
            queue / "responses",
            reports,
            promotion.READY,
            promotion.REQUESTS,
            promotion.HISTORY,
            promotion.ATTESTATIONS,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.attestation_patch = mock.patch.object(promotion, "attest_commit", side_effect=self._attest)
        self.attestation_patch.start()

    def tearDown(self) -> None:
        self.attestation_patch.stop()
        deployment_queue.QUEUE_ROOT = self.old["queue_root"]
        deployment_queue.REPORT_ROOT = self.old["report_root"]
        deployment_queue.RESERVE_PATH = self.old["reserve"]
        deployment_queue.SIGNING_KEY = self.old["key"]
        deployment_queue._promotion_v3 = self.old["promotion_import"]
        promotion.ROOT = self.old["root"]
        promotion.READY = self.old["ready"]
        promotion.REQUESTS = self.old["requests"]
        promotion.HISTORY = self.old["history"]
        promotion.ATTESTATIONS = self.old["attestations"]
        promotion.ACTIVE = self.old["active"]
        promotion.LOCK = self.old["lock"]
        promotion.SHARED_PROMOTION_LEASE = self.old["shared"]
        promotion._started = self.old["started"]
        promotion._last_background_error = self.old["background_error"]
        self.temp.cleanup()

    def _attest(self, commit_sha: str, *, allow_cache: bool = True) -> dict:
        commit = deployment_queue.validate_commit(commit_sha)
        pr = 301 if commit == SHA_A else 302
        return {
            "schema": "pdp-one.promotion-attestation.v3",
            "repository": "PDP-WEBBASE/PDP-One",
            "commit_sha": commit,
            "main_sha": SHA_B,
            "pull_request": pr,
            "changed_files": ["services/pdp_mcp/server.py"],
            "required_workflows": [
                "PDP One Application Boundary Governance",
                "PDP One CI",
                "Build immutable PDP One images",
            ],
            "workflow_evidence": {},
            "priority": "infrastructure",
            "priority_rank": 10,
            "checked_at": promotion._iso(),
            "authoritative_source": "github-api",
            "read_token_used": False,
        }

    def _params(self, commit: str, suffix: str) -> dict:
        return {
            "commit_sha": commit,
            "deployment_id": f"promotion-{suffix}",
            "preview_id": f"preview-{suffix}",
        }

    def _write_response(self, agent_request_id: str, action: str, status: str = "succeeded", **extra) -> None:
        payload = {"request_id": agent_request_id, "action": action, "status": status, **extra}
        (deployment_queue.QUEUE_ROOT / "responses" / f"{agent_request_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_stable_legacy_deploy_is_managed_and_second_candidate_waits(self) -> None:
        first = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_A, "a"))
        self.assertTrue(first["promotion_managed"])
        self.assertNotEqual(first["request_id"], first["agent_request_id"])
        self.assertEqual(len(list((deployment_queue.QUEUE_ROOT / "incoming").glob("*.json"))), 1)
        status = promotion.status_snapshot()
        self.assertFalse(status["legacy_deploy_bypass_allowed"])
        self.assertEqual(status["active_ticket"]["commit_sha"], SHA_A)
        self.assertTrue(promotion.SHARED_PROMOTION_LEASE.exists())

        second = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_C, "c"))
        self.assertTrue(second["promotion_managed"])
        self.assertEqual(second["status"], "pending")
        self.assertEqual(second["promotion_state"], "waiting_promotion")
        self.assertEqual(len(list((deployment_queue.QUEUE_ROOT / "incoming").glob("*.json"))), 1)
        self.assertEqual(promotion.status_snapshot()["ready_count"], 1)

        duplicate = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_C, "c"))
        self.assertEqual(duplicate["request_id"], second["request_id"])
        self.assertEqual(promotion.status_snapshot()["ready_count"], 1)

    def test_exact_deploy_and_health_evidence_move_forward_to_premerge(self) -> None:
        deployed = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_A, "a"))
        self._write_response(deployed["agent_request_id"], "deploy_approved_release")
        deployment_report = deployment_queue.get_response(deployed["request_id"])
        self.assertEqual(deployment_report["promotion_state"], "acceptance")
        self.assertEqual(promotion.status_snapshot()["active_ticket"]["state"], "acceptance")

        health = deployment_queue.enqueue(
            "check_deployment_health", {"deployment_id": "promotion-a"}
        )
        self.assertTrue(health["promotion_managed"])
        self._write_response(health["agent_request_id"], "check_deployment_health")
        health_report = deployment_queue.get_response(health["request_id"])
        self.assertEqual(health_report["promotion_state"], "succeeded")
        self.assertEqual(promotion.status_snapshot()["active_ticket"]["state"], "pre_merge")

        # Reading the older deployment report again must not regress PRE-MERGE.
        deployment_queue.get_response(deployed["request_id"])
        self.assertEqual(promotion.status_snapshot()["active_ticket"]["state"], "pre_merge")

    def test_generic_current_health_does_not_claim_exact_acceptance(self) -> None:
        deployed = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_A, "a"))
        self._write_response(deployed["agent_request_id"], "deploy_approved_release")
        deployment_queue.get_response(deployed["request_id"])
        generic = deployment_queue.enqueue("check_deployment_health", {"deployment_id": "current"})
        self.assertNotIn("promotion_managed", generic)
        self.assertEqual(promotion.status_snapshot()["active_ticket"]["state"], "acceptance")

    def test_existing_v2_lease_blocks_v3_dispatch_and_joins_ready_pool(self) -> None:
        promotion.SHARED_PROMOTION_LEASE.parent.mkdir(parents=True, exist_ok=True)
        promotion._atomic_json(
            promotion.SHARED_PROMOTION_LEASE,
            {
                "schema": "pdp-one.promotion-lease.v2",
                "workstream_id": "legacy-v2-holder",
                "candidate_id": "cand-old",
                "head_sha": SHA_A,
                "expires_at": (promotion._now() + timedelta(hours=1)).isoformat(),
            },
        )
        queued = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_C, "c"))
        self.assertEqual(queued["promotion_state"], "waiting_promotion")
        self.assertEqual(len(list((deployment_queue.QUEUE_ROOT / "incoming").glob("*.json"))), 0)
        self.assertEqual(promotion.status_snapshot()["ready_count"], 1)

    def test_scheduler_rechecks_main_and_marks_waiting_refresh_without_deploy(self) -> None:
        first = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_A, "a"))
        second = deployment_queue.enqueue("deploy_approved_release", self._params(SHA_C, "c"))
        with promotion._mutation_lock():
            active = promotion._active_ticket_unlocked()
            active["state"] = "cancelled"
            promotion._archive_active_unlocked(active)
        (deployment_queue.QUEUE_ROOT / "incoming" / f"{first['agent_request_id']}.json").unlink(missing_ok=True)

        with mock.patch.object(
            promotion,
            "attest_commit",
            side_effect=promotion.PromotionAttestationError("Candidate is behind current main."),
        ):
            promotion._dispatch_waiting_candidate()
        report = promotion.public_request_status(second["request_id"])
        self.assertEqual(report["promotion_state"], "waiting_refresh")
        self.assertEqual(len(list((deployment_queue.QUEUE_ROOT / "incoming").glob("*.json"))), 0)

    def test_authoritative_attestation_requires_exact_pr_main_and_workflows(self) -> None:
        self.attestation_patch.stop()

        def github(path: str):
            if path == "branches/main":
                return {"commit": {"sha": SHA_B}}
            if path == f"commits/{SHA_A}/pulls":
                return [{"number": 401, "state": "open", "head": {"sha": SHA_A}, "base": {"ref": "main"}}]
            if path == f"compare/{SHA_B}...{SHA_A}":
                return {"behind_by": 0}
            if path.startswith("pulls/401/files"):
                return [{"filename": "services/pdp_mcp/server.py"}]
            if path.startswith("actions/runs?"):
                return {
                    "workflow_runs": [
                        {"id": 11, "name": "PDP One Application Boundary Governance", "status": "completed", "conclusion": "success"},
                        {"id": 12, "name": "PDP One CI", "status": "completed", "conclusion": "success"},
                        {"id": 13, "name": "Build immutable PDP One images", "status": "completed", "conclusion": "success"},
                    ]
                }
            raise AssertionError(path)

        with mock.patch.object(promotion, "_github_json", side_effect=github):
            value = promotion.attest_commit(SHA_A, allow_cache=False)
        self.assertEqual(value["main_sha"], SHA_B)
        self.assertEqual(value["pull_request"], 401)
        self.assertEqual(value["workflow_evidence"]["PDP One CI"]["run_id"], 12)

        def stale(path: str):
            if path == "branches/main":
                return {"commit": {"sha": SHA_B}}
            if path == f"commits/{SHA_A}/pulls":
                return [{"number": 401, "state": "open", "head": {"sha": SHA_A}, "base": {"ref": "main"}}]
            if path == f"compare/{SHA_B}...{SHA_A}":
                return {"behind_by": 1}
            raise AssertionError(path)

        with mock.patch.object(promotion, "_github_json", side_effect=stale):
            with self.assertRaisesRegex(promotion.PromotionAttestationError, "behind current main"):
                promotion.attest_commit(SHA_A, allow_cache=False)

        self.attestation_patch = mock.patch.object(promotion, "attest_commit", side_effect=self._attest)
        self.attestation_patch.start()

    def test_image_requirement_matches_pull_request_ignore_boundary(self) -> None:
        self.assertFalse(promotion._image_evidence_required(["scripts/windows/Test.ps1", "tests/x.test.mjs", "README.md"]))
        self.assertTrue(promotion._image_evidence_required(["services/pdp_mcp/server.py"]))
        self.assertTrue(promotion._image_evidence_required(["app/procurement/page.tsx"]))


if __name__ == "__main__":
    unittest.main()
