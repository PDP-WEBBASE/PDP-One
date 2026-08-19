#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$StartupTaskName = "PDP One Stable Startup",
    [string]$NetworkRecoveryTaskName = "PDP One Network Recovery",
    [string]$OpenWebTaskName = "PDP One Open Local Web",
    [string]$McpWatchdogTaskName = "PDP One MCP Self Heal",
    [string]$DiskGuardTaskName = "PDP One Disk Guard"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$startScript = Join-Path $ProjectRoot "scripts\windows\Start-PDPOne.ps1"
$rancherStartupScript = Join-Path $ProjectRoot "scripts\windows\Start-PDPOneRancherResilient.ps1"
$openScript = Join-Path $ProjectRoot "scripts\windows\Open-PDPOneLocal.ps1"
$mcpWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneMcpHealthy.ps1"
$diskGuardScript = Join-Path $ProjectRoot "scripts\windows\Invoke-PDPOneDiskGuard.ps1"
if (-not (Test-Path -LiteralPath $startScript)) { throw "Stable startup script was not found." }
if (-not (Test-Path -LiteralPath $rancherStartupScript)) { throw "Resilient Rancher startup helper was not found." }
if (-not (Test-Path -LiteralPath $openScript)) { throw "Local web opener script was not found." }
if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }
if (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "Disk guard script was not found." }

$startupArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
$startupAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $startupArguments
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
# Stable startup now allows one long initial Rancher/Docker wait plus one bounded
# rdctl shutdown/start recovery cycle. The 30-minute execution envelope prevents
# Task Scheduler from killing a legitimate slow Windows/WSL/Rancher boot.
$settings = New-ScheduledTaskSettingsSet -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $StartupTaskName -Action $startupAction -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings -Description "Starts PDP One after Windows logon and rechecks it every ten minutes. It tolerates slow Rancher startup, performs one bounded non-destructive Rancher recovery, preserves data and tokens, repairs Tailscale Funnel, and writes safe diagnostics on failure." -Force | Out-Null

# A NetworkProfile connection event gives PDP One an immediate second chance when
# Wi-Fi/Ethernet becomes connected after logon. The global stable-startup mutex
# suppresses overlap if the logon/watchdog instance is already running.
$networkCommand = "powershell.exe $startupArguments"
$networkEventFilter = "*[System[Provider[@Name='Microsoft-Windows-NetworkProfile'] and EventID=10000]]"
& schtasks.exe /Create /TN $NetworkRecoveryTaskName /TR $networkCommand /SC ONEVENT /EC "Microsoft-Windows-NetworkProfile/Operational" /MO $networkEventFilter /RL HIGHEST /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The PDP One network-recovery Scheduled Task could not be registered."
}

# Begin health polling immediately at logon. Open-PDPOneLocal waits until local
# health is actually ready, so a fixed sleep only delays already-healthy boots.
$openArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$openScript`" -TimeoutSeconds 300"
$openAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $openArguments
$openTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$openSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $OpenWebTaskName -Action $openAction -Trigger $openTrigger -Principal $principal -Settings $openSettings -Description "Begins polling PDP One local health immediately after logon and opens localhost on the first healthy response without changing Windows DNS." -Force | Out-Null

$mcpArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$mcpWatchdogScript`" -ProjectRoot `"$ProjectRoot`""
$mcpAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $mcpArguments
$mcpLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$mcpPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$mcpSettings = New-ScheduledTaskSettingsSet -RestartCount 6 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 6) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $principal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs the MCP Docker image, verifies imports, recreates only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null

$diskGuardArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$diskGuardScript`" -Mode scheduled -ProjectRoot `"$ProjectRoot`""
$diskGuardAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $diskGuardArguments
$diskGuardDailyTrigger = New-ScheduledTaskTrigger -Daily -At 3:15am
$diskGuardSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DiskGuardTaskName -Action $diskGuardAction -Trigger $diskGuardDailyTrigger -Principal $principal -Settings $diskGuardSettings -Description "Maintains safe C drive capacity for PDP One. It prunes only unused build cache, images, stopped containers and networks, archives old restore-verified backups, compacts Rancher WSL VHDX only when needed, and never prunes Docker volumes." -Force | Out-Null

Write-Host "Scheduled Tasks '$StartupTaskName', '$NetworkRecoveryTaskName', '$OpenWebTaskName', '$McpWatchdogTaskName' and '$DiskGuardTaskName' are installed." -ForegroundColor Green
