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

test("local page polling begins immediately and advisory maintenance is outside the readiness path", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const task = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");

  assert.doesNotMatch(task, /Start-Sleep -Seconds 75/);
  assert.match(task, /-File `"\$openScript`" -TimeoutSeconds 300/);
  assert.match(task, /Begins polling PDP One local health immediately after logon/);

  const healthIndex = startup.indexOf("Test-PDPOne.ps1");
  const diskGuardIndex = startup.indexOf("Invoke-PDPOneDiskGuard.ps1");
  assert.ok(healthIndex >= 0, "layered health check must remain present");
  assert.ok(diskGuardIndex > healthIndex, "advisory startup disk guard must run after readiness checks");
});

test("deployed startup source self-applies the versioned host task policy once", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");

  assert.match(startup, /startup-task-policy\.version/);
  assert.match(startup, /2026-08-20-autonomous-ops-v3/);
  assert.match(startup, /Register-PDPOneStartupTask\.ps1/);
  assert.match(startup, /installedPolicyVersion -ne \$startupPolicyVersion/);
  assert.match(startup, /startup_task_policy = "updated"/);
  assert.match(startup, /startup_task_policy = "current"/);
  assert.match(startup, /startup_task_policy_warning/);
});
