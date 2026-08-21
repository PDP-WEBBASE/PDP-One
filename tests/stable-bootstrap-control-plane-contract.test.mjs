import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');

const server = read('services', 'pdp_mcp', 'server.py');
const queue = read('services', 'pdp_mcp', 'deployment_queue.py');
const wrapper = read('scripts', 'windows', 'Invoke-PDPOneDeployment.ps1');
const reconcile = read('scripts', 'windows', 'Invoke-PDPOneExactAgentReconciliation.ps1');
const compatibility = read('scripts', 'windows', 'Test-PDPOneExactCandidateCompatibility.ps1');
const watchdog = read('scripts', 'windows', 'Ensure-PDPOneDeploymentAgentHealthy.ps1');
const contract = JSON.parse(read('release', 'deployment-agent-compatibility.json'));

test('the long-lived deploy tool keeps its stable schema and signed action', () => {
  assert.match(server, /async def deploy_approved_release\(commit_sha: str, deployment_id: str, preview_id: str\)/);
  assert.match(server, /return enqueue\(\s*"deploy_approved_release"/s);
  assert.match(queue, /"deploy_approved_release"/);
  assert.doesNotMatch(server, /async def deploy_approved_release\([^)]*(?:command|shell|path|executable)/i);
});

test('stable deploy path self-reconciles only safe exact Agent drift before production deployment', () => {
  assert.match(wrapper, /"SAFE_RECONCILABLE"/);
  assert.match(wrapper, /Invoke-PDPOneExactAgentReconciliation\.ps1/);
  assert.match(wrapper, /Exact Agent reconciliation failed before production deployment/);
  assert.match(wrapper, /strict compatibility verification did not reach MATCH/);
  assert.match(wrapper, /"PROTOCOL_MISMATCH"/);
  assert.match(wrapper, /compatibility is unsafe\. No production changes were made/);
  assert.doesNotMatch(wrapper, /Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
});

test('exact reconciliation is fixed-purpose, exact-commit, manifest-bound, and rollback safe', () => {
  assert.match(reconcile, /ValidatePattern\('\^\[0-9a-f\]\{40\}\$'\)/);
  assert.match(reconcile, /PDP-WEBBASE\/PDP-One\/commits\/\$CommitSha/);
  assert.match(reconcile, /deployment-agent-compatibility\.json\?ref=\$CommitSha/);
  assert.match(reconcile, /\^scripts\/windows\/\[A-Za-z0-9\._-\]\+\\\.ps1\$/);
  assert.match(reconcile, /System\.Management\.Automation\.Language\.Parser/);
  assert.match(reconcile, /Get-FileHash[^\n]+SHA256/);
  assert.match(reconcile, /agent-reconcile-backups/);
  assert.match(reconcile, /rollback_attempted/);
  assert.match(reconcile, /rollback_succeeded/);
  assert.match(reconcile, /production_changed = \$false/);
  assert.match(reconcile, /restart_deferred_to_deployment_response = \$true/);
  assert.doesNotMatch(reconcile, /\$Command|\$Action|\$Executable|Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
});

test('compatibility classifier fails closed and separates match, safe reconcile, protocol mismatch, and unsafe', () => {
  assert.match(compatibility, /classification = "MATCH"/);
  assert.match(compatibility, /classification = "SAFE_RECONCILABLE"/);
  assert.match(compatibility, /classification = "PROTOCOL_MISMATCH"/);
  assert.match(compatibility, /classification = "UNSAFE"/);
  assert.match(compatibility, /production_changed = \$false/);
  assert.match(compatibility, /Migration-stage compatibility manifests are never eligible for automatic Agent reconciliation/);
  assert.match(compatibility, /"Invoke-PDPOneScopedRegistryDeployment\.ps1"/);
});

test('steady state protects all nine installed bootstrap files', () => {
  assert.equal(contract.schema, 'pdp-one.deployment-agent-compatibility.v1');
  assert.equal(contract.protocol_version, 1);
  assert.equal(Object.hasOwn(contract, 'migration_stage'), false);
  assert.equal(Object.hasOwn(contract, 'migration_note'), false);
  assert.equal(contract.bootstrap_files.length, 9);
  assert.deepEqual(contract.bootstrap_files.map((entry) => entry.agent_file).sort(), [
    'Deployment-Agent.Standard.ps1',
    'Invoke-PDPOneDeployment.ps1',
    'Invoke-PDPOneManagedFastDeployment.ps1',
    'Invoke-PDPOneScopedRegistryDeployment.ps1',
    'Invoke-PDPOneExactAgentReconciliation.ps1',
    'PDPOne.Common.ps1',
    'PDPOne.OperationLock.ps1',
    'PDPOne.ReleaseManifest.ps1',
    'Test-PDPOneExactCandidateCompatibility.ps1',
  ].sort());
});

test('watchdog and old deployment-status tool expose sanitized capability evidence without observing ChatGPT cache', () => {
  assert.match(watchdog, /stable_operational_interface_revision = "pdp-one\.stable-bootstrap-control-plane\.v1"/);
  assert.match(watchdog, /agent_self_reconcile_capable/);
  assert.match(watchdog, /agent_candidate_compatibility/);
  assert.match(queue, /STABLE_OPERATIONAL_INTERFACE_REVISION = "pdp-one\.stable-bootstrap-control-plane\.v1"/);
  assert.match(queue, /"agent_capabilities": capabilities/);
  assert.match(queue, /"connected_tool_schema_observable": False/);
  assert.match(queue, /"connected_tool_schema_revision": None/);
  assert.match(queue, /"schema_refresh_required": None/);
  assert.match(queue, /"schema_refresh_required_for_bootstrap": False/);
});

test('a stale Connected App catalog containing only the old deploy tool still has a complete bootstrap path', () => {
  assert.match(server, /async def deploy_approved_release/);
  assert.match(wrapper, /SAFE_RECONCILABLE/);
  assert.match(wrapper, /Invoke-PDPOneExactAgentReconciliation\.ps1/);
  assert.match(reconcile, /Assert-ExactSteadyStateManifest/);
  assert.doesNotMatch(wrapper + reconcile, /new_tool_required|schema_refresh_required\s*=\s*true/i);
});
