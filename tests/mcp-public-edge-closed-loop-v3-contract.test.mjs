import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const watchdog = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Ensure-PDPOnePublicEdgeHealthy.ps1'), 'utf8');
const observer = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Observe-PDPOneMcpRoute.ps1'), 'utf8');
const register = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Register-PDPOneStartupTask.ps1'), 'utf8');
const managedDeploy = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Invoke-PDPOneManagedFastDeployment.ps1'), 'utf8');

test('public edge watchdog is evidence-gated by the passive observer incident', () => {
  assert.match(watchdog, /mcp-route-observability/);
  assert.match(watchdog, /IncidentFailureThreshold\s*=\s*3/);
  assert.match(watchdog, /active_incident/);
  assert.match(watchdog, /consecutive_failures/);
  assert.match(watchdog, /CP-01/);
  assert.match(watchdog, /CP-05/);
  assert.match(watchdog, /CP-06/);
  assert.match(watchdog, /CP-10/);
  assert.match(watchdog, /local_runtime_failure_not_edge_repaired/);
  assert.match(watchdog, /healthy_or_not_confirmed/);
  assert.match(observer, /passive_only\s*=\s*\$true/);
  assert.match(observer, /repair_actions\s*=\s*0/);
});

test('closed-loop repair escalates from soft reconcile to one bounded edge recreate', () => {
  const soft = watchdog.indexOf('-RepairAttempts 1 -AllowPersistentMcpEscalation');
  const bounded = watchdog.indexOf('-RepairAttempts 2 -AgentRoot');
  assert.ok(soft >= 0, 'soft reconcile must be present');
  assert.ok(bounded > soft, 'bounded edge recreate must happen only after soft reconcile');
  assert.match(watchdog, /recovered_after_soft_reconcile/);
  assert.match(watchdog, /recovered_after_bounded_edge_recreate/);
  assert.match(watchdog, /RepairCooldownSeconds\s*=\s*900/);
  assert.match(watchdog, /Global\\PDP-One-Public-Edge-V3/);
  assert.match(watchdog, /repair_suppressed_deployment/);
  assert.match(watchdog, /incident_in_cooldown/);
});

test('public edge recovery preserves credentials, identity and data boundaries', () => {
  for (const source of [watchdog, register, managedDeploy]) {
    assert.doesNotMatch(source, /tailscale\s+logout/i);
    assert.doesNotMatch(source, /TAILSCALE_AUTHKEY|rotate_mcp_token/i);
    assert.doesNotMatch(source, /docker\s+(?:volume|system)\s+prune/i);
    assert.doesNotMatch(source, /wsl\s+--unregister|rdctl\s+factory-reset/i);
    assert.doesNotMatch(source, /Invoke-Expression|\biex\b/i);
  }
  assert.match(watchdog, /token_rotated\s*=\s*\$false/);
  assert.match(watchdog, /tailscale_identity_reset\s*=\s*\$false/);
  assert.match(watchdog, /database_changed\s*=\s*\$false/);
  assert.match(watchdog, /docker_volumes_touched\s*=\s*\$false/);
});

test('host policy runs passive observer and public edge watchdog every minute', () => {
  assert.match(register, /2026-08-28-public-edge-closed-loop-v7/);
  assert.match(register, /PDP One MCP Route Observability/);
  assert.match(register, /PDP One Public Edge Watchdog/);
  assert.match(register, /Ensure-PDPOnePublicEdgeHealthy\.ps1/);
  const edgeStart = register.indexOf('$publicEdgeWatchdogPeriodicTrigger');
  assert.ok(edgeStart >= 0);
  const edgeBlock = register.slice(edgeStart, edgeStart + 900);
  assert.match(edgeBlock, /RepetitionInterval \(New-TimeSpan -Minutes 1\)/);
  assert.match(edgeBlock, /MultipleInstances IgnoreNew/);
  assert.match(register, /Assert-PDPOneScheduledTaskWindowless/);
});

test('exact deployment reconciles current Windows task policy before acceptance', () => {
  assert.match(managedDeploy, /reconciling-startup-task-policy/);
  assert.match(managedDeploy, /Register-PDPOneStartupTask\.ps1/);
  assert.match(managedDeploy, /-ApplyIfNeeded/);
  assert.match(managedDeploy, /startup_task_policy_reconciled/);
  const deployment = managedDeploy.indexOf('deploying-exact-commit');
  const reconciliation = managedDeploy.indexOf('reconciling-startup-task-policy');
  assert.ok(deployment >= 0 && reconciliation > deployment);
});
