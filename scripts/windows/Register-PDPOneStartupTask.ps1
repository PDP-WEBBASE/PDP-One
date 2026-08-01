#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$StartupTaskName = "PDP One Stable Startup",
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
$openScript = Join-Path $ProjectRoot "scripts\windows\Open-PDPOneLocal.ps1"
$mcpWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneMcpHealthy.ps1"
$diskGuardScript = Join-Path $ProjectRoot "scripts\windows\Invoke-PDPOneDiskGuard.ps1"
if (-not (Test-Path -LiteralPath $startScript)) { throw "Stable startup script was not found." }
if (-not (Test-Path -LiteralPath $openScript)) { throw "Local web opener script was not found." }
if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }
if (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "Disk guard script was not found." }

$startupArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
$startupAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $startupArguments
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $StartupTaskName -Action $startupAction -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings -Description "Starts PDP One after Windows logon and rechecks it every ten minutes. It waits for Rancher Desktop, preserves data and tokens, repairs Tailscale Funnel, and writes safe diagnostics on failure." -Force | Out-Null

$openArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"Start-Sleep -Seconds 75; & '$openScript' -TimeoutSeconds 300`""
$openAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $openArguments
$openTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$openSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $OpenWebTaskName -Action $openAction -Trigger $openTrigger -Principal $principal -Settings $openSettings -Description "Waits for PDP One local health after logon and opens the local web page without changing Windows DNS." -Force | Out-Null

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

Write-Host "Scheduled Tasks '$StartupTaskName', '$OpenWebTaskName', '$McpWatchdogTaskName' and '$DiskGuardTaskName' are installed." -ForegroundColor Green
