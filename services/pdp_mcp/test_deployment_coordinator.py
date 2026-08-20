import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path


class DeploymentCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["PDP_DEPLOYMENT_QUEUE"] = self.temp.name
        os.environ["PDP_DEPLOYMENT_AGENT_SIGNING_KEY"] = "k" * 48
        import deployment_queue
        import deployment_coordinator
        importlib.reload(deployment_queue)
        self.coordinator = importlib.reload(deployment_coordinator)

    def tearDown(self):
        self.temp.cleanup()

    def register(self, workstream="work-1", paths=None, surfaces=None):
        return self.coordinator.register_workstream(
            workstream,
            "feature/coordinator-branch",
            paths or ["services/pdp_mcp/new.py"],
            surfaces or ["mcp"],
        )

    def test_soft_locks_are_advisory_and_detect_path_or_surface_overlap(self):
        first = self.register()
        second = self.register("work-2", ["other.py"], ["mcp"])
        self.assertTrue(first["soft_lock"])
        self.assertEqual("conflict", second["state"])
        self.assertEqual("work-1", second["conflicts"][0]["workstream_id"])
        self.assertTrue(second["conflicts"][0]["advisory"])

    def test_exact_deployment_is_durable_and_duplicate_is_suppressed(self):
        self.register()
        first = self.coordinator.queue_exact_deployment(
            "work-1", "a" * 40, "deploy-1", "preview-1"
        )
        duplicate = self.coordinator.queue_exact_deployment(
            "work-1", "a" * 40, "deploy-1", "preview-1"
        )
        self.assertEqual(first["request_id"], duplicate["request_id"])
        self.assertTrue(duplicate["duplicate_suppressed"])
        self.assertEqual(1, len(list((Path(self.temp.name) / "incoming").glob("*.json"))))

    def test_priority_queue_dispatches_next_after_active_request_clears(self):
        self.register("normal-work")
        self.register("critical-work", ["critical.py"], ["host"])
        first = self.coordinator.queue_exact_deployment("normal-work", "a" * 40, "deploy-a", "preview-a")
        second = self.coordinator.queue_exact_deployment("critical-work", "b" * 40, "deploy-b", "preview-b", priority="critical")
        incoming = Path(self.temp.name) / "incoming"
        (incoming / f"{first['request_id']}.json").unlink()
        dispatched = self.coordinator._dispatch_next()
        self.assertEqual(second["request_id"], dispatched["request_id"])

    def test_supersession_requires_explicit_containment_and_safe_flags(self):
        self.register()
        first = self.coordinator.queue_exact_deployment("work-1", "a" * 40, "deploy-a", "preview-a")
        incoming = Path(self.temp.name) / "incoming"
        (incoming / f"{first['request_id']}.json").unlink()
        # Keep an Agent request active so the following candidates remain pending.
        (incoming / "busy.json").write_text("{}", encoding="utf-8")
        older = self.coordinator.queue_exact_deployment("work-1", "b" * 40, "deploy-b", "preview-b")
        newer = self.coordinator.queue_exact_deployment("work-1", "c" * 40, "deploy-c", "preview-c", contains_commits=["b" * 40])
        history = json.loads((self.coordinator.HISTORY / f"{older['request_id']}.json").read_text())
        self.assertEqual("superseded", history["state"])
        self.assertEqual(newer["request_id"], history["superseded_by"])

    def test_dashboard_exposes_parallel_and_serial_invariants(self):
        self.register()
        status = self.coordinator.coordinator_status()
        self.assertTrue(status["parallel_development_allowed"])
        self.assertTrue(status["runtime_deployments_serialized"])
        self.assertFalse(status["arbitrary_shell_allowed"])

    def test_background_dispatcher_is_idempotent_and_daemonized(self):
        self.coordinator.start_dispatcher()
        first = self.coordinator._dispatcher_started
        self.coordinator.start_dispatcher()
        self.assertTrue(first)
        self.assertTrue(self.coordinator._dispatcher_started)

    def test_completed_agent_response_recovers_workstream_state_and_dispatches_next(self):
        self.register("work-1")
        first = self.coordinator.queue_exact_deployment("work-1", "a" * 40, "deploy-a", "preview-a")
        incoming = Path(self.temp.name) / "incoming" / f"{first['request_id']}.json"
        incoming.unlink()
        responses = Path(self.temp.name) / "responses"
        responses.mkdir(exist_ok=True)
        (responses / f"{first['request_id']}.json").write_text(
            json.dumps({"request_id": first["request_id"], "status": "succeeded"}), encoding="utf-8"
        )
        status = self.coordinator.coordinator_status()
        workstream = next(item for item in status["workstreams"] if item["workstream_id"] == "work-1")
        self.assertEqual("succeeded", workstream["state"])


if __name__ == "__main__":
    unittest.main()
