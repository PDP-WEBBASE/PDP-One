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


class DeploymentQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["PDP_DEPLOYMENT_QUEUE"] = self.temp.name
        os.environ["PDP_DEPLOYMENT_AGENT_SIGNING_KEY"] = "k" * 48
        import deployment_queue
        self.queue = importlib.reload(deployment_queue)

    def tearDown(self):
        self.temp.cleanup()

    def _payload_for(self, result):
        path = Path(self.temp.name) / "incoming" / f"{result['request_id']}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        return path, envelope, json.loads(base64.b64decode(envelope["payload_b64"]))

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
