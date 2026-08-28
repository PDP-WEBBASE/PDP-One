import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const watchdog = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Ensure-PDPOnePublicEdgeHealthy.ps1'), 'utf8');
const observer = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Observe-PDPOneMcpRoute.ps1'), 'utf8');
const routeTools = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'route_diagnostics_tools.py'), 'utf8');
const register = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Register-PDPOneStartupTask.ps1'), 'utf8');
const managedDeploy = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Invoke-PDPOneManagedFastDeployment.ps1'), 'utf8');
const agentWatchdog = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Ensure-PDPOneDeploymentAgentHealthy.ps1'), 'utf8');
const agentInstall = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Install-PDPOneDeploymentAgent.ps1'), 'utf8');
const statusExtension = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'public_edge_status.py'), 'utf8');
const server = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'server.py'), 'utf8');
const dockerfile = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'Dockerfile'), 'utf8');
const webDockerfile = fs.readFileSync(path.join(root, 'infra', 'docker', 'web.Dockerfile'), 'utf8');
const imageWorkflow = fs.readFileSync(path.join(root, '.github', 'workflows', 'build-images.yml'), 'utf8');

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

test('closed-loop repair escalates from soft reconcile to at most one bounded edge recreate', () => {
  const soft = watchdog.indexOf('-RepairAttempts 1 -AllowPersistentMcpEscalation');
  const bounded = watchdog.indexOf('-RepairAttempts 2 -AgentRoot');
  assert.ok(soft >= 0, 'soft reconcile must be present');
  assert.ok(bounded > soft, 'bounded edge recreate must happen only after soft reconcile and classification');
  assert.match(watchdog, /host_path_recovered_pending_external_confirmation/);
  assert.match(watchdog, /RepairCooldownSeconds\s*=\s*900/);
  assert.match(watchdog, /Global\\PDP-One-Public-Edge-V3/);
  assert.match(watchdog, /repair_suppressed_deployment/);
  assert.match(watchdog, /incident_in_cooldown/);
});

test('confirmed external Funnel edge failures stop internal recreate loops', () => {
  assert.match(watchdog, /Test-LocalFunnelToNginx/);
  assert.match(watchdog, /wget -q -O- http:\/\/127\.0\.0\.1:80\/healthz/);
  assert.match(watchdog, /PDP One ready/);
  assert.match(watchdog, /TAILSCALE_PUBLIC_EDGE_EXTERNAL_REACHABILITY/);
  assert.match(watchdog, /tailscale_public_edge_failure/);
  assert.match(watchdog, /public_edge_observe_only/);
  assert.match(watchdog, /public_edge_externalized\s*=\s*\$true/);
  const classification = watchdog.indexOf('TAILSCALE_PUBLIC_EDGE_EXTERNAL_REACHABILITY');
  const bounded = watchdog.indexOf('$report.repair_stage = "bounded_edge_recreate"');
  assert.ok(classification >= 0 && bounded > classification, 'external edge classification must be checked before bounded recreate');
});

test('V4 separates immutable incident origin from the current failure classification', () => {
  assert.match(observer, /incident_origin_checkpoint/);
  assert.match(observer, /current_failed_checkpoint/);
  assert.match(observer, /incident_origin_root_cause_classification/);
  assert.match(observer, /current_root_cause_classification/);
  assert.match(observer, /Get-RootCauseClassification -CheckpointId \$currentFailed/);
  assert.match(watchdog, /current_root_cause_classification/);
  assert.match(watchdog, /incident_origin_root_cause_classification/);
});

test('V4 external correlation records only sanitized evidence and gates end-to-end recovery', () => {
  assert.match(routeTools, /pdp-one\.mcp-external-observer\.v1/);
  assert.match(routeTools, /connected_mcp_diagnostic_call/);
  assert.match(routeTools, /secrets_included.*False/);
  assert.doesNotMatch(routeTools, /PDP_MCP_PATH_TOKEN|PDP_PUBLIC_BASE_URL|authorization/i);
  assert.match(observer, /external-observer\.json/);
  assert.match(observer, /host_recovered_pending_external_confirmation/);
  assert.match(observer, /externalConfirmsRecovery/);
  assert.match(observer, /external_correlation_status/);
  assert.match(watchdog, /host_recovered_pending_external_confirmation/);
});

test('cooldown suppresses repair but not current external-edge observation', () => {
  const classification = watchdog.indexOf('TAILSCALE_PUBLIC_EDGE_EXTERNAL_REACHABILITY');
  const cooldown = watchdog.indexOf('$cooldown = Get-CooldownRemaining');
  assert.ok(classification >= 0 && cooldown > classification, 'current edge classification must occur before cooldown suppression');
  assert.match(watchdog, /tailscale_public_edge_failure_in_cooldown/);
  assert.match(watchdog, /cooldown_observe_only/);
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

test('deployment agent keeps processing signed requests while host is on battery', () => {
  for (const source of [agentWatchdog, agentInstall]) {
    assert.match(source, /AllowStartIfOnBatteries/);
    assert.match(source, /DontStopIfGoingOnBatteries/);
  }
  assert.match(agentWatchdog, /task_battery_policy_repaired/);
  assert.match(agentWatchdog, /DisallowStartIfOnBatteries/);
  assert.match(agentWatchdog, /StopIfGoingOnBatteries/);
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

test('stable get_deployment_status gains additive sanitized observer and watchdog summaries', () => {
  assert.match(statusExtension, /mcp_route_observer/);
  assert.match(statusExtension, /public_edge_watchdog/);
  assert.match(statusExtension, /pdp-one\.mcp-route-observability\.v2/);
  assert.match(statusExtension, /pdp-one\.public-edge-watchdog\.v1/);
  assert.match(statusExtension, /passive_only/);
  assert.match(statusExtension, /repair_actions/);
  assert.match(statusExtension, /secrets_included/);
  assert.match(statusExtension, /token_rotated/);
  assert.match(statusExtension, /tailscale_identity_reset/);
  assert.doesNotMatch(statusExtension, /PDP_MCP_PATH_TOKEN|PDP_PUBLIC_BASE_URL|authorization/i);
  assert.match(server, /wrap_get_queue_status/);
  assert.match(server, /server_core\.get_queue_status\s*=\s*wrap_get_queue_status/);
  assert.match(dockerfile, /public_edge_status\.py/);
});

test('immutable MCP and Web images carry explicit component identity metadata', () => {
  assert.match(dockerfile, /LABEL\s+io\.pdpone\.component="mcp"/);
  assert.match(webDockerfile, /LABEL\s+io\.pdpone\.component="web"/);
  assert.match(imageWorkflow, /services\/pdp_mcp\/Dockerfile/);
  assert.match(imageWorkflow, /io\.pdpone\.component/);
  assert.match(imageWorkflow, /component label mismatch for \{component\}/);
  assert.match(imageWorkflow, /io\.pdpone\.component\.fingerprint/);
});

test('healthy one-minute watchdog refreshes the pre-existing stable connectivity surface', () => {
  assert.match(watchdog, /public-mcp-connectivity\.json/);
  assert.match(watchdog, /Update-StableHealthyConnectivityStatus/);
  assert.match(watchdog, /pdp-one\.public-mcp-connectivity\.v1/);
  assert.match(watchdog, /stable_status_refreshed/);
});