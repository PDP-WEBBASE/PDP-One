import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (relative) => readFile(new URL(relative, import.meta.url), "utf8");

test("managed deployment prefers scoped releases while retaining a legacy migration fallback", async () => {
  const managed = await load("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1");
  assert.match(managed, /Invoke-PDPOneScopedRegistryDeployment\.ps1/);
  assert.match(managed, /Invoke-PDPOneRegistryFastDeployment\.ps1/);
  assert.match(managed, /scoped_release_manifest_v1/);
  assert.match(managed, /legacy_exact_sha/);
  assert.match(managed, /active_previous_and_inflight_release_manifests/);
  assert.match(managed, /Enter-PDPOneDeploymentOperation/);
  assert.match(managed, /PDPOne\.DeploymentStateCompatibility\.ps1/);
  assert.match(managed, /Update-PDPOneLegacyDeploymentStateForScopedEngine/);
});

test("deployment agent keeps polling and mutex ownership inside the Scheduled Task process", async () => {
  const wrapper = await load("../scripts/windows/Deployment-Agent.ps1");
  assert.match(wrapper, /Deployment-Agent\.Standard\.ps1/);
  assert.match(wrapper, /& \$delegate -AgentRoot \$AgentRoot -PollSeconds \$PollSeconds -Once/);
  assert.match(wrapper, /do \{/);
  assert.match(wrapper, /Start-Sleep -Seconds \$PollSeconds/);
  assert.doesNotMatch(wrapper, /powershell\.exe\s+@arguments/i);
  assert.doesNotMatch(wrapper, /Start-Process[\s\S]*Deployment-Agent\.Standard/i);
  assert.match(wrapper, /without spawning a detached powershell\.exe/);
});

test("scoped deployment reuses unchanged immutable images and restarts only affected services", async () => {
  const deploy = await load("../scripts/windows/Invoke-PDPOneScopedRegistryDeployment.ps1");
  assert.match(deploy, /Get-PDPOneChangedFilePaths/);
  assert.match(deploy, /Get-PDPOneChangeScope/);
  assert.match(deploy, /Get-PDPOnePreviousImageMap/);
  assert.match(deploy, /serviceChanged/);
  assert.match(deploy, /Get-PDPOneActivationTargets/);
  assert.match(deploy, /@\("backend", "worker", "beat"\)/);
  assert.match(deploy, /@\("compose", "stop"\) \+ \$activationTargets/);
  assert.match(deploy, /"--no-deps"\) \+ \$activationTargets/);
  assert.match(deploy, /\$scope\.topology_sensitive -or \("backend" -in \$changedServices\)/);
  assert.match(deploy, /Test-PDPOneScopedHealth\.ps1/);
  assert.match(deploy, /Write-PDPOneReleaseManifest/);
  assert.match(deploy, /local_image_build_performed = \$false/);
  assert.ok(!deploy.includes('-Arguments @("compose", "build"'));
  assert.doesNotMatch(deploy, /volume\s+prune/i);
});

test("release manifest helper supports legacy exact-SHA and content-addressed component identity", async () => {
  const helper = await load("../scripts/windows/PDPOne.ReleaseManifest.ps1");
  const policy = JSON.parse(await load("../release/component-contexts.json"));
  assert.match(helper, /legacy-exact-sha/);
  assert.match(helper, /content-addressed-v1/);
  assert.match(helper, /Get-PDPOneComponentFingerprint/);
  assert.match(helper, /io\.pdpone\.component\.fingerprint/);
  assert.match(helper, /pdp-one\.release-manifest\.v1/);
  assert.match(helper, /repository_digest/);
  assert.doesNotMatch(helper, /^\s*\$host\s*=/im);
  assert.match(helper, /\$hostChanged = \$false/);
  assert.match(helper, /host = \$hostChanged/);
  assert.deepEqual(Object.keys(policy.components).sort(), ["backend", "mcp", "web"]);
  assert.equal(policy.components.backend.root, "backend");
  assert.equal(policy.components.mcp.root, "services/pdp_mcp");
  assert.equal(policy.components.web.root, ".");
  assert.ok(policy.components.web.exclude_prefixes.includes("backend/"));
  assert.ok(policy.components.web.exclude_prefixes.includes("services/"));
  assert.ok(policy.components.web.exclude_prefixes.includes("scripts/windows/"));
});

test("scope-aware health has fast component profiles but retains full-health fallback", async () => {
  const health = await load("../scripts/windows/Test-PDPOneScopedHealth.ps1");
  assert.match(health, /ValidateSet\("full", "backend", "mcp", "web", "host", "none"\)/);
  assert.match(health, /Test-PDPOne\.ps1/);
  assert.match(health, /manage\.py check --database default/);
  assert.match(health, /mcp\/" \+ \$pathToken \+ "\/healthz/);
  assert.match(health, /pdp-build\.json/);
  assert.match(health, /Test-PDPOnePublicHealth/);
});

test("CI preserves required checks while moving expensive suites behind change scope", async () => {
  const ci = await load("../.github/workflows/ci.yml");
  assert.match(ci, /\n\s+verify:\s*\n/);
  assert.match(ci, /name:\s*Windows PowerShell 5\.1 compatibility/);
  assert.match(ci, /name:\s*Fast safety preflight/);
  assert.match(ci, /RUN_FAST_CONTRACTS=/);
  assert.match(ci, /Run fast cross-component contracts/);
  assert.match(ci, /if:\s*env\.RUN_NODE == 'true'/);
  assert.match(ci, /Classify Windows compatibility scope/);
  assert.match(ci, /Windows compatibility not affected/);
});

test("host runtime marker explicitly forces the one legacy exact-SHA state-compatibility hotfix publication", async () => {
  const marker = await load("../HOST-RUNTIME-SOURCE");
  assert.match(marker, /v4-scoped-state-compatibility-hotfix-20260819/);
  assert.match(marker, /legacy exact-SHA image publication/);
  assert.match(marker, /legacy-engine fallback/);
});
