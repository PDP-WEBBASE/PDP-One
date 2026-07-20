import importlib
import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
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

    def test_only_allowlisted_action_is_written(self):
        result = self.queue.enqueue("check_deployment_health", {"deployment_id": "d-1"})
        path = Path(self.temp.name) / "incoming" / f"{result['request_id']}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(64, len(envelope["signature"]))
        self.assertNotIn("k" * 48, path.read_text(encoding="utf-8"))
        payload = base64.b64decode(envelope["payload_b64"])
        expected = hmac.new(("k" * 48).encode(), payload, hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(expected, envelope["signature"]))

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
