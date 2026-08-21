import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("stable startup tolerates slow Rancher boot and performs one bounded non-destructive recovery", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const rancher = await load("../scripts/windows/Start-PDPOneRancherResilient.ps1");

  assert.match(startup, /DockerTimeoutSeconds\s*=\s*420/);
  assert.match(startup, /RancherRecoveryTimeoutSeconds\s*=\s*420/);
  assert.match(startup, /Start-PDPOneRancherResilient\.ps1/);
  assert.match(startup, /rancher_startup_report/);
  assert.match(startup, /Global\\PDP-One-Stable-Startup/);

  assert.match(rancher, /InitialTimeoutSeconds\s*=\s*420/);
  assert.match(rancher, /RecoveryTimeoutSeconds\s*=\s*420/);
  assert.match(rancher, /PollSeconds\s*=\s*1/);
  assert.match(rancher, /bounded_restart_attempted/);
  assert.match(rancher, /rdctl\.Source shutdown/);
  assert.match(rancher, /--application\.start-in-background/);
  assert.match(rancher, /--container-engine\.name=moby/);
  assert.match(rancher, /--kubernetes\.enabled=false/);
  assert.match(rancher, /--application\.startInBackground=true/);
  assert.match(rancher, /ready_after_bounded_restart/);

  assert.doesNotMatch(rancher, /factory\s+reset/i);
  assert.doesNotMatch(rancher, /wsl(?:\.exe)?\s+--unregister/i);
  assert.doesNotMatch(rancher, /docker\s+volume\s+(?:rm|prune)/i);
  assert.doesNotMatch(rancher, /tailscale\s+(?:logout|down|up)/i);
});

test("stable startup binds Compose to the last healthy immutable deployment images", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");

  assert.match(startup, /last-deployment\.json/);
  assert.match(startup, /active_images/);
  assert.match(startup, /PDP_BACKEND_IMAGE/);
  assert.match(startup, /PDP_MCP_IMAGE/);
  assert.match(startup, /PDP_WEB_IMAGE/);
  assert.match(startup, /ghcr\.io\/pdp-webbase\/pdp-one-\$service/);
  assert.match(startup, /content-\[0-9a-f\]\{64\}/);
  assert.match(startup, /docker image inspect \$image/);
  assert.match(startup, /Stable Startup will not pull or build a substitute/);
  assert.match(startup, /--pull never/);

  const acceptedStateIndex = startup.indexOf("last-deployment.json");
  const composeConfigIndex = startup.indexOf("docker compose config --quiet");
  assert.ok(acceptedStateIndex >= 0, "accepted deployment state must be read");
  assert.ok(composeConfigIndex > acceptedStateIndex, "accepted image identities must be bound before Compose resolves services");

  assert.doesNotMatch(startup, /docker\s+(?:pull|build)\b/i);
  assert.doesNotMatch(startup, /docker\s+volume\s+(?:rm|prune)/i);
  assert.doesNotMatch(startup, /tailscale\s+logout/i);
});

test("startup task retries immediately on Windows network connection and keeps a periodic fallback", async () => {
  const task = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");

  assert.match(task, /PDP One Network Recovery/);
  assert.match(task, /Microsoft-Windows-NetworkProfile\/Operational/);
  assert.match(task, /EventID=10000/);
  assert.match(task, /\/SC ONEVENT/);
  assert.match(task, /\/RL HIGHEST/);
  assert.match(task, /ExecutionTimeLimit \(New-TimeSpan -Minutes 30\)/);
  assert.match(task, /RepetitionInterval \(New-TimeSpan -Minutes 10\)/);
  assert.match(task, /MultipleInstances IgnoreNew/);
  assert.match(task, /StartWhenAvailable/);
});

test("all PDP One background Scheduled Task registration paths use the windowless launcher", async () => {
  const registration = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");
  const installer = await load("../scripts/windows/Install-PDPOneDeploymentAgent.ps1");
  const watchdog = await load("../scripts/windows/Ensure-PDPOneDeploymentAgentHealthy.ps1");
  const health = await load("../scripts/windows/Test-PDPOneScopedHealth.ps1");
  const helper = await load("../scripts/windows/PDPOne.HiddenTask.ps1");
  const runner = await load("../scripts/windows/Run-PDPOneHidden.vbs");

  assert.match(helper, /System32\\wscript\.exe/);
  assert.match(helper, /New-PDPOneHiddenPowerShellAction/);
  assert.match(helper, /Assert-PDPOneScheduledTaskWindowless/);
  assert.match(helper, /Test-PDPOneScheduledTaskWindowless/);
  assert.match(runner, /CreateObject\("WScript\.Shell"\)/);
  assert.match(runner, /shell\.Run\(command, 0, True\)/);

  assert.match(registration, /New-PDPOneHiddenPowerShellAction/);
  assert.match(registration, /System32\\wscript\.exe/);
  assert.match(registration, /-LogonType Interactive -RunLevel Highest/);
  assert.doesNotMatch(registration, /New-ScheduledTaskAction\s+-Execute\s+"powershell\.exe"/i);
  assert.match(installer, /New-PDPOneHiddenPowerShellAction/);
  assert.doesNotMatch(installer, /New-ScheduledTaskAction\s+-Execute\s+"powershell\.exe"/i);
  assert.match(watchdog, /New-PDPOneHiddenPowerShellAction/);
  assert.match(watchdog, /task_action_repaired/);
  assert.doesNotMatch(watchdog, /New-ScheduledTaskAction\s+-Execute\s+"powershell\.exe"/i);
  assert.match(health, /Ensure-PDPOneWindowlessTaskAcceptance/);
  assert.match(health, /Assert-PDPOneScheduledTaskWindowless/);
  assert.match(health, /New-PDPOneHiddenPowerShellAction/);
  assert.doesNotMatch(health, /New-ScheduledTaskAction\s+-Execute\s+"powershell\.exe"/i);

  assert.match(registration, /RepetitionInterval \(New-TimeSpan -Minutes 1\)/);
  assert.match(registration, /RepetitionInterval \(New-TimeSpan -Minutes 5\)/);
  assert.match(registration, /RepetitionInterval \(New-TimeSpan -Minutes 10\)/);
  assert.match(registration, /-Daily -At 3:15am/);
});

test("local page polling begins immediately and advisory maintenance is outside the readiness path", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const task = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");

  assert.doesNotMatch(task, /Start-Sleep -Seconds 75/);
  assert.match(task, /New-PDPOneHiddenPowerShellAction -ScriptPath \$openScript -ScriptArguments @\("-TimeoutSeconds", "300"\)/);
  assert.match(task, /Begins polling PDP One local health immediately after logon/);

  const healthIndex = startup.indexOf("Test-PDPOne.ps1");
  const diskGuardIndex = startup.indexOf("Invoke-PDPOneDiskGuard.ps1");
  assert.ok(healthIndex >= 0, "layered health check must remain present");
  assert.ok(diskGuardIndex > healthIndex, "advisory startup disk guard must run after readiness checks");
});

test("deployed startup source recognizes the new windowless host task policy", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const registration = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");

  assert.match(startup, /startup-task-policy\.version/);
  assert.match(startup, /2026-08-21-hidden-background-tasks-v5/);
  assert.match(startup, /Register-PDPOneStartupTask\.ps1/);
  assert.match(startup, /installedPolicyVersion -ne \$startupPolicyVersion/);
  assert.match(startup, /startup_task_policy = "updated"/);
  assert.match(startup, /startup_task_policy = "current"/);
  assert.match(startup, /startup_task_policy_warning/);
  assert.match(registration, /2026-08-21-hidden-background-tasks-v5/);
  assert.match(registration, /ApplyIfNeeded/);
});
