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

  const standardProtected = contract.bootstrap_files.some((entry) => entry.agent_file === "Deployment-Agent.Standard.ps1");
  if (contract.migration_stage === "autonomous-privileged-ops-stage-a") {
    assert.equal(standardProtected, false, "Stage A may omit only Standard so the current protected Agent can bootstrap its fixed self-sync action");
    assert.match(String(contract.migration_note || ""), /Stage B immediately restores Standard/i);
    const protectedFiles = contract.bootstrap_files.map((entry) => entry.agent_file).sort();
    assert.deepEqual(protectedFiles, [
      "Invoke-PDPOneDeployment.ps1",
      "Invoke-PDPOneManagedFastDeployment.ps1",
      "Invoke-PDPOneScopedRegistryDeployment.ps1",
      "PDPOne.Common.ps1",
      "PDPOne.OperationLock.ps1",
      "PDPOne.ReleaseManifest.ps1",
      "Test-PDPOneExactCandidateCompatibility.ps1",
    ].sort());
  } else {
    assert.equal(standardProtected, true, "Deployment-Agent.Standard.ps1 must remain protected outside the one explicit Stage A migration");
  }

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


test("one-command exact candidate promotion survives MCP recreation and never merges", async () => {
  const promotion = await readFile(new URL("../services/pdp_mcp/exact_candidate_promotion_tools.py", import.meta.url), "utf8");
  const queue = await readFile(new URL("../services/pdp_mcp/deployment_queue.py", import.meta.url), "utf8");
  const agent = await readFile(new URL("../scripts/windows/Deployment-Agent.Standard.ps1", import.meta.url), "utf8");
  const server = await readFile(new URL("../services/pdp_mcp/server.py", import.meta.url), "utf8");
  const dockerfile = await readFile(new URL("../services/pdp_mcp/Dockerfile", import.meta.url), "utf8");

  assert.match(server, /register_exact_candidate_promotion_tools/);
  assert.match(server, /from exact_candidate_promotion_tools import register_exact_candidate_promotion_tools/);
  assert.match(dockerfile, /COPY[^\n]*exact_candidate_promotion_tools\.py[^\n]*\.\//);
  assert.match(promotion, /async def promote_exact_candidate/);
  assert.match(promotion, /get_queue_status\(\)/);
  assert.match(promotion, /pending_requests/);
  assert.match(promotion, /enqueue\(\s*"promote_exact_candidate"/s);
  assert.match(promotion, /durable_windows_orchestration/);
  assert.match(promotion, /includes_independent_health/);
  assert.match(promotion, /automatic_merge/);
  assert.match(promotion, /fresh PRE-MERGE Delta\/Concurrency Sync/i);
  assert.doesNotMatch(promotion, /asyncio|_wait_for_agent_response|merge_pull_request|subprocess|os\.system|shell=True/);

  assert.match(queue, /"promote_exact_candidate": 1800/);
  assert.match(queue, /"promote_exact_candidate",/);
  assert.match(queue, /\{"deploy_approved_release", "promote_exact_candidate"\}/);

  assert.match(agent, /"promote_exact_candidate"\s*\{/);
  assert.match(agent, /Test-PDPOneDevelopmentFastMode/);
  assert.match(agent, /Invoke-PDPOneDeployment\.ps1/);
  assert.match(agent, /-DevelopmentFastMode/);
  assert.match(agent, /Test-PDPOne\.ps1/);
  assert.match(agent, /SkipChatGPTToolCheck/);
  assert.match(agent, /runtime_accepted = \$true/);
  assert.match(agent, /automatic_merge = \$false/);
  assert.match(agent, /premerge_required = \$true/);
  assert.match(agent, /MCP; orchestration remains in the Windows Agent/);
  assert.doesNotMatch(agent, /docker\s+volume\s+prune/i);
});
