import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const agent = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Deployment-Agent.Standard.ps1'), 'utf8');
const tools = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'exact_candidate_promotion_tools.py'), 'utf8');
const scopedHealth = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Test-PDPOneScopedHealth.ps1'), 'utf8');
const watchdogSelfTest = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Test-PDPOneDeploymentAgentWatchdogSelfHeal.ps1'), 'utf8');
const contract = JSON.parse(fs.readFileSync(path.join(root, 'release', 'deployment-agent-compatibility.json'), 'utf8'));

const privilegedActions = [
  'sync_agent_from_exact_commit',
  'ensure_pdp_one_started',
  'repair_pdp_one_connectivity',
  'collect_pdp_one_diagnostics',
];

test('privileged MCP surface is a fixed signed enum and never arbitrary shell', () => {
  for (const action of privilegedActions) {
    assert.match(tools, new RegExp(`"${action}"`), `missing MCP allowlisted action ${action}`);
    assert.match(agent, new RegExp(`"${action}"\\s*\\{`), `missing Windows Agent action ${action}`);
  }
  assert.match(tools, /async def sync_deployment_agent_from_exact_commit\(commit_sha: str\)/);
  assert.match(tools, /commit = validate_commit\(commit_sha\)/);
  assert.doesNotMatch(tools, /async def sync_deployment_agent_from_exact_commit\([^)]*(?:command|shell|path)/i);
  assert.doesNotMatch(agent, /Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
});

test('Agent sync is exact-commit, manifest-bound, parse-checked and rollback-protected', () => {
  const start = agent.indexOf('"sync_agent_from_exact_commit" {');
  const end = agent.indexOf('"ensure_pdp_one_started" {', start);
  assert.ok(start >= 0 && end > start, 'sync action block must exist');
  const block = agent.slice(start, end);

  assert.match(block, /\^\[0-9a-f\]\{40\}\$/);
  assert.match(block, /PDP-WEBBASE\/PDP-One\/commits\/\$commit/);
  assert.match(block, /pdp-one\.deployment-agent-compatibility\.v1/);
  assert.match(block, /protocol_version\s+-ne\s+1/);
  assert.match(block, /\^scripts\/windows\/\[A-Za-z0-9\._-\]\+\\\.ps1\$/);
  assert.match(block, /Deployment-Agent\.Standard\.ps1/);
  assert.match(block, /System\.Management\.Automation\.Language\.Parser/);
  assert.match(block, /Get-FileHash[^\n]+SHA256/);
  assert.match(block, /agent-sync-backups/);
  assert.match(block, /rollback_on_sync_failure\s*=\s*\$true/);
  assert.match(block, /restart-agent-after-response/);
});

test('normal operations remain bounded and sensitive identities are preserved', () => {
  const repairStart = agent.indexOf('"repair_pdp_one_connectivity" {');
  const repairEnd = agent.indexOf('"collect_pdp_one_diagnostics" {', repairStart);
  const repair = agent.slice(repairStart, repairEnd);
  assert.match(repair, /RepairAttempts 1/);
  assert.match(repair, /identity_reset = \$false/);
  assert.match(repair, /credential_rotation = \$false/);

  const maintenanceStart = agent.indexOf('"run_disk_maintenance" {');
  const maintenanceEnd = agent.indexOf('"rollback_deployment" {', maintenanceStart);
  const maintenance = agent.slice(maintenanceStart, maintenanceEnd);
  assert.match(maintenance, /IsNullOrWhiteSpace\(\[string\]\$backupPathProperty\.Value\)/);
  assert.doesNotMatch(maintenance, /Test-Path\s+-LiteralPath\s+\(\[string\]\$deploymentState\.backup_path\)/);
});

test('exact-release health self-registers, windowless-checks and acceptance-checks the fixed Agent watchdog', () => {
  assert.match(scopedHealth, /Ensure-PDPOneWindowlessTaskAcceptance/);
  assert.match(scopedHealth, /Register-PDPOneStartupTask\.ps1/);
  assert.match(scopedHealth, /PDP One Local Deployment Agent/);
  assert.match(scopedHealth, /PDP One Deployment Agent Watchdog/);
  assert.match(scopedHealth, /Assert-PDPOneScheduledTaskWindowless/);
  assert.match(scopedHealth, /Test-PDPOneScheduledTaskWindowless/);
  assert.match(scopedHealth, /New-PDPOneHiddenPowerShellAction/);
  assert.match(scopedHealth, /Start-ScheduledTask -TaskName \$watchdogTaskName/);
  assert.match(scopedHealth, /deployment-agent-watchdog\.json/);
  assert.match(scopedHealth, /pdp-one\.deployment-agent-watchdog\.v1/);
  assert.match(scopedHealth, /task_state_after -eq "Running"/);
  assert.match(scopedHealth, /PDP One Deployment Agent Watchdog Self Test/);
  assert.match(scopedHealth, /Register-ScheduledTask -TaskName \$selfTestTaskName/);
  assert.match(scopedHealth, /deployment-agent-watchdog-selftest-v1\.accepted/);
  assert.doesNotMatch(scopedHealth, /New-ScheduledTaskAction\s+-Execute\s+"powershell\.exe"/i);
  assert.doesNotMatch(scopedHealth, /Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
});

test('watchdog self-test is bounded, lane-aware and fails safe', () => {
  assert.match(watchdogSelfTest, /PDP One Local Deployment Agent/);
  assert.match(watchdogSelfTest, /PDP One Deployment Agent Watchdog/);
  assert.match(watchdogSelfTest, /deployment-in-progress\.json/);
  assert.match(watchdogSelfTest, /queue\\incoming/);
  assert.match(watchdogSelfTest, /Stop-ScheduledTask -TaskName \$AgentTaskName/);
  assert.match(watchdogSelfTest, /recovered_by_watchdog = \$true/);
  assert.match(watchdogSelfTest, /safety_fallback_started = \$true/);
  assert.match(watchdogSelfTest, /Start-ScheduledTask -TaskName \$AgentTaskName/);
  assert.match(watchdogSelfTest, /deployment-agent-watchdog-selftest-v1\.accepted/);
  assert.match(watchdogSelfTest, /Unregister-ScheduledTask -TaskName \$SelfTestTaskName/);
  assert.doesNotMatch(watchdogSelfTest, /Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
  assert.doesNotMatch(watchdogSelfTest, /docker\s+(?:volume|system)\s+prune|tailscale\s+logout|Remove-Item[^\n]+\.env/i);
});

test('steady-state compatibility protects all ten bootstrap files', () => {
  assert.equal(contract.schema, 'pdp-one.deployment-agent-compatibility.v1');
  assert.equal(contract.protocol_version, 1);
  assert.equal(Object.hasOwn(contract, 'migration_stage'), false);
  assert.equal(Object.hasOwn(contract, 'migration_note'), false);
  const files = contract.bootstrap_files.map((entry) => entry.agent_file).sort();
  assert.deepEqual(files, [
    'Deployment-Agent.Standard.ps1',
    'Invoke-PDPOneDeployment.ps1',
    'Invoke-PDPOneManagedFastDeployment.ps1',
    'Invoke-PDPOneZeroDowntimeRegistryDeployment.ps1',
    'Invoke-PDPOneScopedRegistryDeployment.ps1',
    'Invoke-PDPOneExactAgentReconciliation.ps1',
    'PDPOne.Common.ps1',
    'PDPOne.OperationLock.ps1',
    'PDPOne.ReleaseManifest.ps1',
    'Test-PDPOneExactCandidateCompatibility.ps1',
  ].sort());
});