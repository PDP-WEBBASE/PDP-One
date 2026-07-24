#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$StartupTaskName = "PDP One Stable Startup",
    [string]$OpenWebTaskName = "PDP One Open Local Web"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$startScript = Join-Path $ProjectRoot "scripts\windows\Start-PDPOne.ps1"
$openScript = Join-Path $ProjectRoot "scripts\windows\Open-PDPOneLocal.ps1"
if (-not (Test-Path -LiteralPath $startScript)) { throw "Stable startup script was not found." }
if (-not (Test-Path -LiteralPath $openScript)) { throw "Local web opener script was not found." }

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

Write-Host "Scheduled Tasks '$StartupTaskName' and '$OpenWebTaskName' are installed." -ForegroundColor Green
