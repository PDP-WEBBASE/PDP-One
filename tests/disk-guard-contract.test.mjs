import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("disk guard is structural, advisory, and never prunes Docker volumes", async () => {
  const guard = await readFile(new URL("../scripts/windows/Invoke-PDPOneDiskGuard.ps1", import.meta.url), "utf8");
  const startup = await readFile(new URL("../scripts/windows/Start-PDPOne.ps1", import.meta.url), "utf8");
  const deploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneDeployment.ps1", import.meta.url), "utf8");
  const managed = await readFile(new URL("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", import.meta.url), "utf8");
  const registration = await readFile(new URL("../scripts/windows/Register-PDPOneStartupTask.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");

  assert.doesNotMatch(guard, /volume\s+prune/i);
  assert.doesNotMatch(guard, /system\s+prune/i);
  assert.match(guard, /capacity_gate_enforced = \$false/);
  assert.match(guard, /deployment_allowed = \$true/);
  assert.match(guard, /actual_write_failure_stops_deployment = \$true/);
  assert.match(guard, /CleanupThresholdGB = 10/);
  assert.match(guard, /KeepLocalFinalBackups = 2/);
  assert.match(guard, /Optimize-VHD/);
  assert.match(guard, /compact vdisk/);
  assert.match(guard, /restore_verified/);
  assert.match(startup, /Invoke-PDPOneDiskGuard\.ps1.*-Mode startup/s);
  assert.match(deploy, /Invoke-PDPOneManagedFastDeployment\.ps1/);
  assert.match(managed, /-Mode predeploy/);
  assert.match(managed, /-Mode postdeploy/);
  assert.match(registration, /PDP One Disk Guard/);
  assert.match(registration, /New-PDPOneHiddenPowerShellAction -ScriptPath \$diskGuardScript -ScriptArguments @\("-Mode", "scheduled", "-ProjectRoot", \$ProjectRoot\)/);
  assert.match(compose, /max-size: "10m"/);
  assert.match(compose, /max-file: "3"/);
  assert.ok((compose.match(/logging: \*pdp-logging/g) || []).length >= 8);
});
