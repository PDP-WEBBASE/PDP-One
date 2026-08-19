import importlib
import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


class DeploymentQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.reports_temp = tempfile.TemporaryDirectory()
        os.environ["PDP_DEPLOYMENT_QUEUE"] = self.temp.name
        os.environ["PDP_DEPLOYMENT_REPORTS"] = self.reports_temp.name
        os.environ["PDP_DEPLOYMENT_AGENT_SIGNING_KEY"] = "k" * 48
        os.environ["PDP_QUEUE_RESERVE_BYTES"] = str(1024 * 1024)
        os.environ["PDP_QUEUE_LOW_SPACE_BYTES"] = str(512 * 1024)
        import deployment_queue
        self.queue = importlib.reload(deployment_queue)

    def tearDown(self):
        self.temp.cleanup()
        self.reports_temp.cleanup()
        os.environ.pop("PDP_DEPLOYMENT_REPORTS", None)
        os.environ.pop("PDP_QUEUE_RESERVE_BYTES", None)
        os.environ.pop("PDP_QUEUE_LOW_SPACE_BYTES", None)

    def _payload_for(self, result):
        path = Path(self.temp.name) / "incoming" / f"{result['request_id']}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        return path, envelope, json.loads(base64.b64decode(envelope["payload_b64"]))

    def _write_failed_deployment_evidence(self, deployment_id="deploy-001"):
        queued = self.queue.enqueue(
            "deploy_approved_release",
            {"commit_sha": "a" * 40, "deployment_id": deployment_id, "preview_id": "preview-1"},
        )
        request_path = Path(self.temp.name) / "incoming" / f"{queued['request_id']}.json"
        rejected_root = Path(self.temp.name) / "rejected"
        rejected_root.mkdir(parents=True, exist_ok=True)
        request_path.replace(rejected_root / request_path.name)
        responses_root = Path(self.temp.name) / "responses"
        responses_root.mkdir(parents=True, exist_ok=True)
        (responses_root / f"{queued['request_id']}.json").write_text(
            json.dumps(
                {
                    "request_id": queued["request_id"],
                    "action": "deploy_approved_release",
                    "status": "failed",
                    "completed_at": "2026-08-19T18:00:00+00:00",
                    "result": {"error": "Deployment failed; see the rollback result in the deployment report."},
                }
            ),
            encoding="utf-8",
        )
        report = {
            "schema": "pdp-one.deployment-report.v3",
            "deployment_id": deployment_id,
            "preview_id": "preview-1",
            "approved_commit": "a" * 40,
            "previous_commit": "b" * 40,
            "status": "failed",
            "stage": "pulling-immutable-images",
            "image_mode": "content-addressed-v1",
            "production_changed": False,
            "health_profile": "full",
            "changed_services": ["backend", "mcp", "web"],
            "changed_paths": ["release/component-image-mode.json"],
            "active_images": {"backend": "ghcr.io/pdp-webbase/pdp-one-backend:content-" + "c" * 64},
            "error": "Bearer secret-value github_pat_private-token image fingerprint mismatch",
            "release_manifest": "C:/ProgramData/PDP-One/deployment-agent/state/release-manifests/private.json",
            "private_path": "C:/private/not-for-mcp",
        }
        (Path(self.reports_temp.name) / f"{deployment_id}.json").write_text(json.dumps(report), encoding="utf-8")
        return queued

    def test_only_allowlisted_action_is_written(self):
        result = self.queue.enqueue("check_deployment_health", {"deployment_id": "d-1"})
        path, envelope, payload = self._payload_for(result)
        self.assertEqual(64, len(envelope["signature"]))
        self.assertNotIn("k" * 48, path.read_text(encoding="utf-8"))
        payload_bytes = base64.b64decode(envelope["payload_b64"])
        expected = hmac.new(("k" * 48).encode(), payload_bytes, hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(expected, envelope["signature"]))
        self.assertEqual("check_deployment_health", payload["action"])

    def test_health_action_gets_extended_lifetime(self):
        result = self.queue.enqueue("check_deployment_health", {"deployment_id": "d-1"})
        _, _, payload = self._payload_for(result)
        created = datetime.fromisoformat(payload["created_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
        self.assertEqual(1800, int((expires - created).total_seconds()))

    def test_other_actions_keep_standard_lifetime(self):
        result = self.queue.enqueue("verify_backup_restore", {"backup_id": "sample"})
        _, _, payload = self._payload_for(result)
        created = datetime.fromisoformat(payload["created_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
        self.assertEqual(300, int((expires - created).total_seconds()))

    def test_lifetime_above_safety_cap_is_rejected(self):
        with self.assertRaises(ValueError):
            self.queue.enqueue("check_deployment_health", {}, ttl_seconds=1801)

    def test_arbitrary_action_is_rejected(self):
        with self.assertRaises(ValueError):
            self.queue.enqueue("run_powershell", {"command": "whoami"})

    def test_signed_disk_maintenance_is_allowlisted(self):
        result = self.queue.enqueue("run_disk_maintenance", {"keep_local_final_backups": 2})
        _, _, payload = self._payload_for(result)
        self.assertEqual("run_disk_maintenance", payload["action"])
        self.assertEqual(2, payload["params"]["keep_local_final_backups"])

    def test_low_disk_releases_reserve_and_allows_only_maintenance(self):
        queue_root = Path(self.temp.name)
        queue_root.mkdir(parents=True, exist_ok=True)
        self.queue.RESERVE_PATH.write_bytes(b"x" * 4096)
        with patch.object(self.queue, "_disk_free_bytes", return_value=0):
            result = self.queue.enqueue("run_disk_maintenance", {"keep_local_final_backups": 2})
        self.assertTrue(result["emergency_reserve_released"])
        self.assertFalse(self.queue.RESERVE_PATH.exists())

        self.queue.RESERVE_PATH.write_bytes(b"x" * 4096)
        with patch.object(self.queue, "_disk_free_bytes", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "storage is full"):
                self.queue.enqueue("deploy_approved_release", {})

    def test_queue_status_reports_disk_headroom(self):
        self.queue.enqueue("check_deployment_health", {"deployment_id": "d-1"})
        status = self.queue.get_queue_status()
        self.assertIn("disk_free_bytes", status)
        self.assertIn("low_disk_space", status)
        self.assertIn("emergency_reserve_available", status)

    def test_failed_deployment_response_includes_only_sanitized_whitelisted_report(self):
        queued = self._write_failed_deployment_evidence()
        result = self.queue.get_response(queued["request_id"])
        report = result["deployment_report"]
        self.assertEqual("deploy-001", report["deployment_id"])
        self.assertEqual("pulling-immutable-images", report["stage"])
        self.assertEqual("content-addressed-v1", report["image_mode"])
        self.assertIn("[REDACTED]", report["error"])
        self.assertNotIn("secret-value", report["error"])
        self.assertNotIn("github_pat_private-token", report["error"])
        self.assertNotIn("release_manifest", report)
        self.assertNotIn("private_path", report)

    def test_failed_report_is_not_enriched_if_rejected_envelope_signature_is_tampered(self):
        queued = self._write_failed_deployment_evidence("deploy-002")
        rejected = Path(self.temp.name) / "rejected" / f"{queued['request_id']}.json"
        envelope = json.loads(rejected.read_text(encoding="utf-8"))
        envelope["signature"] = "0" * 64
        rejected.write_text(json.dumps(envelope), encoding="utf-8")
        result = self.queue.get_response(queued["request_id"])
        self.assertNotIn("deployment_report", result)

    def test_commit_must_be_exact_sha(self):
        with self.assertRaises(ValueError):
            self.queue.validate_commit("main")
        self.assertEqual("a" * 40, self.queue.validate_commit("A" * 40))

    def test_identifiers_cannot_escape_agent_directories(self):
        for value in ("../outside", "a/b", "", "x" * 65):
            with self.assertRaises(ValueError):
                self.queue.validate_identifier(value, "deployment_id")
        self.assertEqual("deploy-001", self.queue.validate_identifier("deploy-001", "deployment_id"))


if __name__ == "__main__":
    unittest.main()
