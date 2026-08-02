import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("fast deployment is not blocked by a fixed free-space threshold", async () => {
  const guard = await read("scripts/windows/Invoke-PDPOneDiskGuard.ps1");
  const dispatcher = await read("scripts/windows/Invoke-PDPOneDeployment.ps1");
  const managed = await read("scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1");

  assert.match(guard, /capacity_gate_enforced\s*=\s*\$false/);
  assert.match(guard, /deployment_allowed\s*=\s*\$true/);
  assert.match(guard, /actual_write_failure_stops_deployment\s*=\s*\$true/);
  assert.match(dispatcher, /Invoke-PDPOneManagedFastDeployment\.ps1/);
  assert.match(managed, /-Mode predeploy/);
  assert.match(managed, /-Mode postdeploy/);
  assert.match(managed, /obsolete_artifacts_cleaned_immediately/);
});

test("obsolete Rancher artifacts are pruned while active, previous, and in-flight images and all volumes are retained", async () => {
  const guard = await read("scripts/windows/Invoke-PDPOneDiskGuard.ps1");
  const compose = await read("docker-compose.yml");

  assert.match(guard, /builder", "prune", "--all", "--force", "--keep-storage"/);
  assert.match(guard, /active_previous_and_inflight_commit/);
  assert.match(guard, /Get-PDPOneInFlightCommit/);
  assert.match(guard, /image", "rm", \$reference/);
  assert.match(guard, /image", "prune", "--force"/);
  assert.doesNotMatch(guard, /image", "prune", "--all"/);
  assert.match(guard, /container", "prune", "--force/);
  assert.match(guard, /network", "prune", "--force/);
  assert.doesNotMatch(guard, /volume", "prune/);
  assert.doesNotMatch(guard, /docker\s+volume\s+prune/i);
  assert.match(guard, /KeepLocalFinalBackups = 2/);
  assert.match(guard, /D:\\BackUp PDP-0NE-14050429-01/);
  assert.match(compose, /driver: local/);
  assert.match(compose, /max-size: "10m"/);
  assert.match(compose, /max-file: "3"/);
});