from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "scripts/windows/Start-PDPOne.ps1",
    '    diagnostics = $null\n}',
    '    diagnostics = $null\n    disk_guard_report = $null\n}',
)
replace_once(
    "scripts/windows/Start-PDPOne.ps1",
    '    $ProjectRoot = Get-PDPOneProjectRoot\n    Set-Location $ProjectRoot\n    Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds',
    '    $ProjectRoot = Get-PDPOneProjectRoot\n    Set-Location $ProjectRoot\n    $diskGuardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1") -Mode startup -ProjectRoot $ProjectRoot)\n    if ($LASTEXITCODE -ne 0) { throw "PDP One disk guard blocked startup because C: free space is unsafe." }\n    if ($diskGuardOutput.Count -gt 0) { $report.disk_guard_report = [string]$diskGuardOutput[-1] }\n    Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds',
)

replace_once(
    "scripts/windows/Invoke-PDPOneDeployment.ps1",
    'Set-StrictMode -Version Latest\n\nif ($DevelopmentFastMode) {',
    'Set-StrictMode -Version Latest\n\n$diskGuardScript = Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1"\nif (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "The PDP One disk guard is missing." }\n& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $diskGuardScript -Mode predeploy\nif ($LASTEXITCODE -ne 0) { throw "Deployment was blocked because C: free space is below the safe build threshold." }\n\nif ($DevelopmentFastMode) {',
)

replace_once(
    "scripts/windows/Register-PDPOneStartupTask.ps1",
    '    [string]$OpenWebTaskName = "PDP One Open Local Web",\n    [string]$McpWatchdogTaskName = "PDP One MCP Self Heal"',
    '    [string]$OpenWebTaskName = "PDP One Open Local Web",\n    [string]$McpWatchdogTaskName = "PDP One MCP Self Heal",\n    [string]$DiskGuardTaskName = "PDP One Disk Guard"',
)
replace_once(
    "scripts/windows/Register-PDPOneStartupTask.ps1",
    '$mcpWatchdogScript = Join-Path $ProjectRoot "scripts\\windows\\Ensure-PDPOneMcpHealthy.ps1"\nif (-not (Test-Path -LiteralPath $startScript))',
    '$mcpWatchdogScript = Join-Path $ProjectRoot "scripts\\windows\\Ensure-PDPOneMcpHealthy.ps1"\n$diskGuardScript = Join-Path $ProjectRoot "scripts\\windows\\Invoke-PDPOneDiskGuard.ps1"\nif (-not (Test-Path -LiteralPath $startScript))',
)
replace_once(
    "scripts/windows/Register-PDPOneStartupTask.ps1",
    'if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }',
    'if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }\nif (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "Disk guard script was not found." }',
)
replace_once(
    "scripts/windows/Register-PDPOneStartupTask.ps1",
    'Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $principal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs the MCP Docker image, verifies imports, recreates only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null\n\nWrite-Host "Scheduled Tasks \'$StartupTaskName\', \'$OpenWebTaskName\' and \'$McpWatchdogTaskName\' are installed." -ForegroundColor Green',
    'Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $principal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs the MCP Docker image, verifies imports, recreates only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null\n\n$diskGuardArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$diskGuardScript`" -Mode scheduled -ProjectRoot `"$ProjectRoot`""\n$diskGuardAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $diskGuardArguments\n$diskGuardDailyTrigger = New-ScheduledTaskTrigger -Daily -At 3:15am\n$diskGuardSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew -StartWhenAvailable\nRegister-ScheduledTask -TaskName $DiskGuardTaskName -Action $diskGuardAction -Trigger $diskGuardDailyTrigger -Principal $principal -Settings $diskGuardSettings -Description "Maintains safe C drive capacity for PDP One. It prunes only unused build cache, images, stopped containers and networks, archives old restore-verified backups, compacts Rancher WSL VHDX only when needed, and never prunes Docker volumes." -Force | Out-Null\n\nWrite-Host "Scheduled Tasks \'$StartupTaskName\', \'$OpenWebTaskName\', \'$McpWatchdogTaskName\' and \'$DiskGuardTaskName\' are installed." -ForegroundColor Green',
)

compose = ROOT / "docker-compose.yml"
text = compose.read_text(encoding="utf-8")
if "x-pdp-logging: &pdp-logging" not in text:
    text = text.replace(
        "name: pdp-one\n\nservices:\n",
        'name: pdp-one\n\nx-pdp-logging: &pdp-logging\n  driver: json-file\n  options:\n    max-size: "10m"\n    max-file: "3"\n\nservices:\n',
        1,
    )
text = text.replace(
    "    restart: unless-stopped\n",
    "    restart: unless-stopped\n    logging: *pdp-logging\n",
)
compose.write_text(text, encoding="utf-8")

(ROOT / "tests/disk-guard-contract.test.mjs").write_text(
    '''import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("disk guard is structural and never prunes Docker volumes", async () => {
  const guard = await readFile(new URL("../scripts/windows/Invoke-PDPOneDiskGuard.ps1", import.meta.url), "utf8");
  const startup = await readFile(new URL("../scripts/windows/Start-PDPOne.ps1", import.meta.url), "utf8");
  const deploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneDeployment.ps1", import.meta.url), "utf8");
  const registration = await readFile(new URL("../scripts/windows/Register-PDPOneStartupTask.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");

  assert.doesNotMatch(guard, /volume\\s+prune/i);
  assert.doesNotMatch(guard, /system\\s+prune/i);
  assert.match(guard, /MinimumDeployFreeGB = 8/);
  assert.match(guard, /CleanupThresholdGB = 10/);
  assert.match(guard, /KeepLocalFinalBackups = 2/);
  assert.match(guard, /Optimize-VHD/);
  assert.match(guard, /compact vdisk/);
  assert.match(guard, /restore_verified/);
  assert.match(startup, /Invoke-PDPOneDiskGuard\\.ps1.*-Mode startup/s);
  assert.match(deploy, /Invoke-PDPOneDiskGuard\\.ps1/);
  assert.match(deploy, /-Mode predeploy/);
  assert.match(registration, /PDP One Disk Guard/);
  assert.match(registration, /-Mode scheduled/);
  assert.match(compose, /max-size: "10m"/);
  assert.match(compose, /max-file: "3"/);
  assert.ok((compose.match(/logging: \\*pdp-logging/g) || []).length >= 8);
});
''',
    encoding="utf-8",
)

print("Structural PDP One disk guard patch applied")
