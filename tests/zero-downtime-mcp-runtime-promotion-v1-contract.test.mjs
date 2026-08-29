import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const engine = fs.readFileSync('scripts/windows/Invoke-PDPOneZeroDowntimeRegistryDeployment.ps1', 'utf8');
const managed = fs.readFileSync('scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1', 'utf8');
const nginx = fs.readFileSync('infra/nginx/default.conf.template', 'utf8');
const compatibility = JSON.parse(fs.readFileSync('release/deployment-agent-compatibility.json', 'utf8'));

function at(text, needle) {
  const index = text.indexOf(needle);
  assert.notEqual(index, -1, `missing required contract marker: ${needle}`);
  return index;
}

test('managed deployment prefers the zero-downtime engine and keeps safe fallbacks', () => {
  assert.match(managed, /Invoke-PDPOneZeroDowntimeRegistryDeployment\.ps1/);
  assert.match(managed, /zero_downtime_overlap_v1/);
  assert.ok(at(managed, 'Test-Path -LiteralPath $zeroDowntimeScript') < at(managed, 'Test-Path -LiteralPath $scopedScript'));
  assert.match(managed, /Invoke-PDPOneScopedRegistryDeployment\.ps1/);
  assert.match(managed, /Invoke-PDPOneRegistryFastDeployment\.ps1/);
});

test('Agent compatibility manifest protects the new engine', () => {
  const entry = compatibility.bootstrap_files.find((item) => item.path === 'scripts/windows/Invoke-PDPOneZeroDowntimeRegistryDeployment.ps1');
  assert.ok(entry);
  assert.equal(entry.agent_file, 'Invoke-PDPOneZeroDowntimeRegistryDeployment.ps1');
});

test('nginx supports a non-secret graceful runtime upstream override', () => {
  assert.match(nginx, /set \$pdp_backend_upstream backend:8000;/);
  assert.match(nginx, /set \$pdp_mcp_upstream mcp:8010;/);
  assert.match(nginx, /include \/etc\/nginx\/pdp-runtime-upstreams\/\*\.conf;/);
});

test('candidate readiness happens before traffic switch', () => {
  const backendReady = at(engine, 'Wait-PDPOneCandidateHttp -Container $backendCandidate');
  const mcpReady = at(engine, 'Wait-PDPOneCandidateHttp -Container $mcpCandidate');
  const switchTraffic = at(engine, 'Set-PDPOneNginxRuntimeUpstreams -BackendTarget $backendTarget -McpTarget $mcpCandidate');
  assert.ok(backendReady < switchTraffic);
  assert.ok(mcpReady < switchTraffic);
  assert.match(engine, /readiness_before_switch=\$true/);
});

test('backend changes always receive an MCP continuity candidate', () => {
  assert.match(engine, /\$needsMcpContinuity=\("backend" -in \$changedServices\) -or \("mcp" -in \$changedServices\)/);
  assert.match(engine, /PDP_API_URL=http:\/\/"\+\$backendTarget\+":8000\/api\/v1/);
});

test('traffic is moved with graceful nginx reload, never an nginx or tailscale restart', () => {
  assert.match(engine, /"nginx","-s","reload"/);
  assert.doesNotMatch(engine, /compose[^\n]+stop[^\n]+nginx/);
  assert.doesNotMatch(engine, /compose[^\n]+stop[^\n]+tailscale/);
  assert.doesNotMatch(engine, /force-recreate[^\n]+nginx/);
  assert.doesNotMatch(engine, /force-recreate[^\n]+tailscale/);
  assert.match(engine, /nginx_restarted=\$false/);
  assert.match(engine, /tailscale_restarted=\$false/);
});

test('canonical backend and MCP are recreated only after candidate stabilization', () => {
  const switchTraffic = at(engine, 'Set-PDPOneNginxRuntimeUpstreams -BackendTarget $backendTarget -McpTarget $mcpCandidate');
  const stabilization = at(engine, '$deadline=(Get-Date).AddSeconds([Math]::Max(1,$StabilizationSeconds))');
  const canonicalBackend = at(engine, '"--force-recreate","backend","worker","beat"');
  const canonicalMcp = at(engine, '"--force-recreate","mcp"');
  assert.ok(switchTraffic < stabilization);
  assert.ok(stabilization < canonicalBackend);
  assert.ok(stabilization < canonicalMcp);
});

test('V1 defaults to a 30 second stabilization window and fails on any continuity gap', () => {
  assert.match(engine, /\[int\]\$StabilizationSeconds = 30/);
  assert.match(engine, /mcp_continuity_probe_failures=0/);
  assert.match(engine, /Continuity probe failed during the stabilization window/);
  assert.match(engine, /zero_downtime_strategy="temporary_candidate_nginx_graceful_switch_v1"/);
});

test('zero-downtime engine never uses stop-before-start for application activation', () => {
  assert.doesNotMatch(engine, /docker[^\n]+compose[^\n]+stop/);
  assert.doesNotMatch(engine, /@\("compose","stop"/);
});

test('security and exact-release invariants remain explicit', () => {
  assert.match(engine, /Get-PDPOneTokenFingerprint/);
  assert.match(engine, /Deployment changed the MCP path token without authorization/);
  assert.match(engine, /Assert-PDPOneReleaseImageIdentity/);
  assert.match(engine, /Write-PDPOneReleaseManifest/);
  assert.match(engine, /secrets_included=\$false/);
});
