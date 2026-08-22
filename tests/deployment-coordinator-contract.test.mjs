import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("multi-chat coordination is durable, advisory and exact-commit only", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /LEGACY_FINAL_STATES/);
  assert.match(coordinator, /pdp-one\.workstream\.v2/);
  assert.match(coordinator, /soft_lock/);
  assert.match(coordinator, /lock_expires_at/);
  assert.match(coordinator, /_coordinator_mutation_lock/);
  assert.match(coordinator, /validate_commit\(commit_sha\)/);
  assert.match(coordinator, /duplicate_suppressed/);
  assert.match(coordinator, /migration_sensitive/);
  assert.match(coordinator, /parallel_development_allowed/);
  assert.match(coordinator, /runtime_deployments_serialized/);
  assert.match(coordinator, /promotion_serialized/);
  assert.match(coordinator, /exact_candidate_evidence_required/);
  assert.match(coordinator, /automatic_cross_chat_takeover/);
  assert.doesNotMatch(coordinator, /subprocess|os\.system|shell\s*=/);
});

test("V2 candidates bind evidence and invalidate stale heads", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /pdp-one\.candidate\.v1/);
  assert.match(coordinator, /workstream_head_changed/);
  assert.match(coordinator, /evidence_state/);
  assert.match(coordinator, /Evidence head SHA does not match the candidate exact head/);
  assert.match(coordinator, /record_workstream_candidate_evidence/);
  assert.match(coordinator, /current_candidate_id/);
});

test("promotion rejects stale main and holds through acceptance", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /Candidate is not integrated on the exact current main/);
  assert.match(coordinator, /Old-base candidate deployment is forbidden/);
  assert.match(coordinator, /promotion-lease\.v1/);
  assert.match(coordinator, /record_development_candidate_acceptance/);
  assert.match(coordinator, /pre_merge/);
  assert.match(coordinator, /deployment_result_candidate_identity_missing/);
});

test("origin continuity is explicit and automatic cross-chat takeover stays disabled", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /origin_chat_ref/);
  assert.match(coordinator, /handoff_history/);
  assert.match(coordinator, /Cross-chat continuation requires an explicit owner-requested handoff/);
  assert.match(coordinator, /automatic_cross_chat_takeover[^\n]*False/);
});

test("dependencies, impact surfaces, live-test leases and priority aging are modeled", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /blocked_by/);
  assert.match(coordinator, /integrates_with/);
  assert.match(coordinator, /runtime_resources/);
  assert.match(coordinator, /database_resources/);
  assert.match(coordinator, /live-test-lease\.v1/);
  assert.match(coordinator, /_effective_priority_rank/);
  assert.match(coordinator, /aging_credit/);
});

test("coordinator tools are registered without weakening stable CI identities", async () => {
  const server = await load("../services/pdp_mcp/server.py");
  const dockerfile = await load("../services/pdp_mcp/Dockerfile");
  const ci = await load("../.github/workflows/ci.yml");
  assert.match(server, /register_deployment_coordinator_tools\(mcp\)/);
  assert.match(dockerfile, /deployment_coordinator\.py/);
  assert.match(ci, /^  verify:$/m);
  assert.match(ci, /^    name: Windows PowerShell 5\.1 compatibility$/m);
});

test("the persistent MCP dispatcher promotes signed requests without an active chat", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /def _dispatcher_loop\(\)/);
  assert.match(coordinator, /threading\.Thread/);
  assert.match(coordinator, /daemon=True/);
  assert.match(coordinator, /start_dispatcher\(\)/);
  assert.match(coordinator, /_dispatch_next_unlocked\(\)/);
  assert.match(coordinator, /_renew_lifecycle_leases_unlocked\(\)/);
  assert.doesNotMatch(coordinator, /subprocess|os\.system|shell\s*=/);
});
