import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("multi-chat coordination is durable, advisory and exact-commit only", async () => {
  const coordinator = await load("../services/pdp_mcp/deployment_coordinator.py");
  assert.match(coordinator, /pdp-one\.workstream\.v1/);
  assert.match(coordinator, /soft_lock/);
  assert.match(coordinator, /lock_expires_at/);
  assert.match(coordinator, /validate_commit\(commit_sha\)/);
  assert.match(coordinator, /duplicate_suppressed/);
  assert.match(coordinator, /migration_sensitive/);
  assert.match(coordinator, /contains_commits/);
  assert.match(coordinator, /parallel_development_allowed/);
  assert.match(coordinator, /runtime_deployments_serialized/);
  assert.match(coordinator, /arbitrary_shell_allowed/);
  assert.doesNotMatch(coordinator, /shell\s*=|subprocess|os\.system/);
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

test("the persistent Windows Agent promotes the next signed request without an active chat", async () => {
  const agent = await load("../scripts/windows/Deployment-Agent.Standard.ps1");
  assert.match(agent, /function Move-NextCoordinatedRequest/);
  assert.match(agent, /queue\\coordinator\\pending/);
  assert.match(agent, /Sort-Object Name/);
  assert.match(agent, /Move-NextCoordinatedRequest \| Out-Null/);
  assert.match(agent, /Test-AgentSignature/);
  assert.doesNotMatch(agent, /Invoke-Expression/);
});
