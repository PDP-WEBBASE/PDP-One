import fs from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const manifest = JSON.parse(fs.readFileSync("release/deployment-agent-compatibility.json", "utf8"));
const preflight = fs.readFileSync("scripts/windows/Test-PDPOneExactCandidateCompatibility.ps1", "utf8");
const reconciliation = fs.readFileSync("scripts/windows/Invoke-PDPOneExactAgentReconciliation.ps1", "utf8");
const managed = fs.readFileSync("scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", "utf8");

const helper = "PDPOne.DeploymentStateCompatibility.ps1";

test("deployment state compatibility helper is a governed bootstrap dependency", () => {
  const names = manifest.bootstrap_files.map((entry) => entry.agent_file);
  assert.ok(names.includes(helper), "deployment state compatibility helper must be present in the compatibility manifest");
  assert.match(preflight, new RegExp(helper.replaceAll(".", "\\.")), "compatibility preflight fixed set must include the helper");
  assert.match(reconciliation, new RegExp(helper.replaceAll(".", "\\.")), "exact agent reconciliation fixed set must include the helper");
  assert.match(managed, /PDPOne\.DeploymentStateCompatibility\.ps1/);
  assert.match(managed, /Update-PDPOneLegacyDeploymentStateForScopedEngine/);
});
