import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("managed deployment holds one shared operation lock through post-deploy cleanup", async () => {
  const helper = await load("../scripts/windows/PDPOne.OperationLock.ps1");
  const managed = await load("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1");

  assert.match(helper, /Global\\PDP-One-Deployment-Operation/);
  assert.match(helper, /deployment-in-progress\.json/);
  assert.match(helper, /target_commit = \$CommitSha/);
  assert.match(helper, /expires_at/);
  assert.match(managed, /Enter-PDPOneDeploymentOperation/);
  assert.match(managed, /Stage "predeploy-cleanup"/);
  assert.match(managed, /Stage "deploying-exact-commit"/);
  assert.match(managed, /Stage "postdeploy-cleanup"/);
  assert.match(managed, /Exit-PDPOneDeploymentOperation/);
  assert.ok(
    managed.indexOf("postdeploy-cleanup") < managed.indexOf("Exit-PDPOneDeploymentOperation"),
    "the lock must remain held until post-deployment cleanup completes",
  );
});

test("disk guard protects active, previous, and in-flight image generations", async () => {
  const guard = await load("../scripts/windows/Invoke-PDPOneDiskGuard.ps1");

  assert.match(guard, /Get-PDPOneInFlightCommit/);
  assert.match(guard, /active_previous_and_inflight_commit/);
  assert.match(guard, /cleanup_skipped_due_to_deployment/);
  assert.match(guard, /Mode -in @\("startup", "scheduled", "emergency"\)/);
  assert.match(guard, /Rancher VHD compaction is disabled while a deployment is in progress/);
  assert.doesNotMatch(guard, /volume\s+prune/i);
});

test("startup and MCP self-heal do not compete with an exact-commit deployment", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const mcp = await load("../scripts/windows/Ensure-PDPOneMcpHealthy.ps1");

  assert.match(startup, /Read-PDPOneDeploymentOperation/);
  assert.match(startup, /skipped_deployment_in_progress/);
  assert.match(mcp, /Read-PDPOneDeploymentOperation/);
  assert.match(mcp, /skipped_deployment_in_progress/);
  assert.match(mcp, /--no-build/);
  assert.match(mcp, /--pull never/);
  assert.doesNotMatch(mcp, /docker compose build/);
  assert.doesNotMatch(mcp, /Repair-McpDockerfile/);
});
