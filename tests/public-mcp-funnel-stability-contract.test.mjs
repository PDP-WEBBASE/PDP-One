import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const repair = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Repair-PDPOneConnectivity.ps1'), 'utf8');
const watchdog = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Ensure-PDPOneMcpHealthy.ps1'), 'utf8');
const queue = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'deployment_queue.py'), 'utf8');

test('persistent public MCP-only degradation has bounded Funnel-only escalation', () => {
  assert.match(repair, /\[switch\]\$AllowPersistentMcpEscalation/);
  assert.match(repair, /\$McpOnlyFailureThreshold\s*=\s*2/);
  assert.match(repair, /\$FunnelRepairCooldownSeconds\s*=\s*900/);
  assert.match(repair, /pdp-one\.public-mcp-connectivity\.v1/);
  assert.match(repair, /Global\\PDP-One-Public-Mcp-Funnel-Repair/);
  assert.match(repair, /Read-PDPOneDeploymentOperation[^\n]+-AgentRoot \$AgentRoot/);
  assert.match(repair, /persistent public MCP-only degradation/);
  assert.match(repair, /funnel", "reset"/);
  assert.match(repair, /funnel", "--bg", "--yes", "80"/);
  assert.match(repair, /last_funnel_repair_at/);
  assert.match(repair, /last_funnel_repair_result/);
  assert.match(repair, /cooldown_seconds_remaining/);
});

test('non-escalating observers do not advance the persistent failure counter', () => {
  const observer = repair.indexOf('if (-not $AllowPersistentMcpEscalation)');
  const increment = repair.indexOf('$state.consecutive_mcp_only_failures = [Math]::Max', observer);
  assert.ok(observer >= 0, 'observer guard must exist');
  assert.ok(increment > observer, 'counter increment must occur only after observer-only return guard');
  const observerBlock = repair.slice(observer, increment);
  assert.match(observerBlock, /does not advance the persistent-failure counter/);
  assert.match(observerBlock, /return Complete-PDPOneConnectivityResult/);
});

test('five-minute MCP watchdog owns escalation but cannot broad-recreate the route', () => {
  assert.match(watchdog, /Repair-PDPOneConnectivity\.ps1[^\n]+-RepairAttempts 1 -AllowPersistentMcpEscalation -AgentRoot \$AgentRoot/);
  assert.match(watchdog, /skipped_deployment_in_progress/);
  assert.match(watchdog, /funnel_registration_reset/);
  assert.match(watchdog, /persistent_mcp_failure_count/);
  assert.match(watchdog, /funnel_repair_cooldown_remaining/);
  assert.doesNotMatch(watchdog, /tailscale\s+logout/i);
  assert.doesNotMatch(watchdog, /volume\s+prune|system\s+prune/i);
});

test('public MCP connectivity observability is sanitized and included in deployment status', () => {
  assert.match(queue, /public-mcp-connectivity\.json/);
  assert.match(queue, /pdp-one\.public-mcp-connectivity\.v1/);
  assert.match(queue, /"public_mcp_connectivity": connectivity/);
  assert.match(queue, /"public_mcp_observed_healthy"/);
  for (const field of [
    'local_mcp',
    'public_web',
    'public_api',
    'public_mcp',
    'dns_state',
    'consecutive_mcp_only_failures',
    'last_funnel_repair_at',
    'last_funnel_repair_result',
    'cooldown_seconds_remaining',
    'repair_suppressed_deployment',
  ]) {
    assert.match(queue, new RegExp(`"${field}"`));
  }
  assert.doesNotMatch(queue, /PDP_MCP_PATH_TOKEN|PDP_PUBLIC_BASE_URL/);
});

test('Funnel escalation preserves identity, credentials and data boundaries', () => {
  assert.doesNotMatch(repair, /tailscale\s+logout/i);
  assert.doesNotMatch(repair, /TAILSCALE_AUTHKEY|rotate_mcp_token|PDP_MCP_TOKEN\s*=/i);
  assert.doesNotMatch(repair, /docker\s+(?:volume|system)\s+prune/i);
  assert.doesNotMatch(repair, /wsl\s+--unregister|rdctl\s+factory-reset/i);
  assert.doesNotMatch(repair, /Invoke-Expression|\biex\b/i);
});
