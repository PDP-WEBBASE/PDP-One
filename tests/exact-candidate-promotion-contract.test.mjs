import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("development-fast compatibility preflight fails closed before production mutation", async () => {
  const managed = await readFile(new URL("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", import.meta.url), "utf8");
  const preflight = await readFile(new URL("../scripts/windows/Test-PDPOneExactCandidateCompatibility.ps1", import.meta.url), "utf8");
  const contract = JSON.parse(await readFile(new URL("../release/deployment-agent-compatibility.json", import.meta.url), "utf8"));

  assert.equal(contract.schema, "pdp-one.deployment-agent-compatibility.v1");
  assert.equal(contract.protocol_version, 1);
  assert.ok(contract.bootstrap_files.length >= 6);
  assert.ok(contract.bootstrap_files.some((entry) => entry.agent_file === "PDPOne.ReleaseManifest.ps1"));
  assert.ok(contract.bootstrap_files.some((entry) => entry.agent_file === "Invoke-PDPOneManagedFastDeployment.ps1"));
  assert.ok(contract.bootstrap_files.some((entry) => entry.agent_file === "Test-PDPOneExactCandidateCompatibility.ps1"));

  const compatibilityStage = managed.indexOf('Stage "deployment-compatibility-preflight"');
  const rancherStage = managed.indexOf('Stage "applying-rancher-policy"');
  const cleanupStage = managed.indexOf('Stage "predeploy-cleanup"');
  const deployStage = managed.indexOf('Stage "deploying-exact-commit"');
  assert.ok(compatibilityStage >= 0);
  assert.ok(compatibilityStage < rancherStage);
  assert.ok(compatibilityStage < cleanupStage);
  assert.ok(compatibilityStage < deployStage);
  assert.match(managed, /production_changed = \$false/);
  assert.match(managed, /Deployment compatibility preflight failed before production changes/);
  assert.match(managed, /compatibility_preflight_passed/);

  assert.match(preflight, /raw\.githubusercontent\.com\/PDP-WEBBASE\/PDP-One\/\$CommitSha/);
  assert.match(preflight, /Get-FileHash -LiteralPath \$candidatePath -Algorithm SHA256/);
  assert.match(preflight, /Get-FileHash -LiteralPath \$installedPath -Algorithm SHA256/);
  assert.match(preflight, /Deployment-agent bootstrap prerequisite mismatch/);
  assert.match(preflight, /production_changed = \$false/);
  assert.doesNotMatch(preflight, /docker\s+volume\s+prune/i);
  assert.doesNotMatch(preflight, /tailscale\s+(logout|down)/i);
});


test("one-command exact candidate promotion composes signed deploy and independent health but never merges", async () => {
  const promotion = await readFile(new URL("../services/pdp_mcp/exact_candidate_promotion_tools.py", import.meta.url), "utf8");
  const server = await readFile(new URL("../services/pdp_mcp/server.py", import.meta.url), "utf8");

  assert.match(server, /register_exact_candidate_promotion_tools/);
  assert.match(promotion, /async def promote_exact_candidate/);
  assert.match(promotion, /get_queue_status\(\)/);
  assert.match(promotion, /pending_requests/);
  assert.match(promotion, /enqueue\(\s*"deploy_approved_release"/s);
  assert.match(promotion, /await _wait_for_agent_response/);
  assert.match(promotion, /enqueue\(\s*"check_deployment_health"/s);
  assert.match(promotion, /"status": "runtime_accepted" if runtime_accepted else "health_not_accepted"/);
  assert.match(promotion, /"automatic_merge": False/);
  assert.match(promotion, /"premerge_required": bool\(runtime_accepted\)/);
  assert.match(promotion, /fresh PRE-MERGE Delta\/Concurrency Sync/i);
  assert.doesNotMatch(promotion, /merge_pull_request/);
  assert.doesNotMatch(promotion, /subprocess|os\.system|shell=True/);
});
