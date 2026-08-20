import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const deployment = fs.readFileSync(
  path.join(root, 'scripts', 'windows', 'Invoke-PDPOneScopedRegistryDeployment.ps1'),
  'utf8',
);

test('Connectivity Edge impact is explicit and fail-closed when scope cannot be resolved', () => {
  assert.match(deployment, /function Test-PDPOneConnectivityEdgeImpact/);
  assert.match(deployment, /if \(\$ConservativeFullStack\) \{ return \$true \}/);
  assert.match(deployment, /\$path -eq "docker-compose\.yml"/);
  assert.match(deployment, /StartsWith\("infra\/nginx\/"/);
  assert.match(deployment, /\$edgeImpact = \[bool\]\(Test-PDPOneConnectivityEdgeImpact/);
});

test('normal application topology activation excludes Nginx and Tailscale', () => {
  assert.match(
    deployment,
    /\$applicationTopologyTargets = @\("backend", "worker", "beat", "mcp", "web"\)/,
  );
  assert.match(
    deployment,
    /if \(\$scope\.topology_sensitive\) \{\s*Invoke-PDPOneNative[^\n]+\(@\("compose", "stop"\) \+ \$applicationTopologyTargets\)/s,
  );
  assert.match(
    deployment,
    /if \(\$scope\.topology_sensitive\) \{\s*Invoke-PDPOneNative[^\n]+\(@\("compose", "up", "--detach", "--no-build", "--pull", "never", "--no-deps"\) \+ \$applicationTopologyTargets\)/s,
  );
  assert.doesNotMatch(
    deployment,
    /"stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale"/,
  );
});

test('Connectivity Edge refresh is gated and bounded', () => {
  const edgeBlockStart = deployment.indexOf('if ($edgeImpact) {', deployment.indexOf('$report.stage = "activating-exact-release"'));
  assert.ok(edgeBlockStart >= 0, 'edge refresh guard must exist after application activation');
  const healthStart = deployment.indexOf('$report.stage = "scope-aware-health-check"', edgeBlockStart);
  assert.ok(healthStart > edgeBlockStart, 'edge refresh must finish before scoped health');
  const edgeBlock = deployment.slice(edgeBlockStart, healthStart);
  assert.match(edgeBlock, /"stop", "tailscale", "nginx"/);
  assert.match(edgeBlock, /"--no-deps", "nginx"/);
  assert.match(edgeBlock, /"--no-deps", "tailscale"/);
  assert.match(edgeBlock, /connectivity_edge_refresh_performed = \$true/);
  assert.match(edgeBlock, /connectivity_edge_preserved = \$false/);
});

test('failed deployment recovery preserves the Edge unless that release impacted it', () => {
  const catchStart = deployment.indexOf('} catch {\n    $report.status = "failed"');
  assert.ok(catchStart >= 0, 'top-level deployment catch block must exist');
  const catchBlock = deployment.slice(catchStart);
  assert.match(
    catchBlock,
    /"db", "redis", "backend", "worker", "beat", "mcp", "web"/,
  );
  assert.match(catchBlock, /if \(\$edgeImpact\) \{/);
  assert.doesNotMatch(
    catchBlock,
    /@\("compose", "--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never"\)\s*-FailureMessage "Services could not be restarted after the failed deployment/,
  );
});

test('deployment report records whether the Edge was impacted, refreshed or preserved', () => {
  for (const field of [
    'connectivity_edge_impacted',
    'connectivity_edge_refresh_performed',
    'connectivity_edge_preserved',
  ]) {
    assert.match(deployment, new RegExp(field));
  }
});

test('edge isolation does not introduce destructive or credential-reset operations', () => {
  assert.doesNotMatch(deployment, /tailscale\s+logout/i);
  assert.doesNotMatch(deployment, /rotate_mcp_token|TAILSCALE_AUTHKEY/i);
  assert.doesNotMatch(deployment, /docker\s+(?:volume|system)\s+prune/i);
  assert.doesNotMatch(deployment, /wsl\s+--unregister|rdctl\s+factory-reset/i);
  assert.doesNotMatch(deployment, /Invoke-Expression|\biex\b/i);
});
