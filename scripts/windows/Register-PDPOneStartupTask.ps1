#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$StartupTaskName = "PDP One Stable Startup",
    [string]$NetworkRecoveryTaskName = "PDP One Network Recovery",
    [string]$OpenWebTaskName = "PDP One Open Local Web",
    [string]$McpWatchdogTaskName = "PDP One MCP Self Heal",
    [string]$DeploymentAgentWatchdogTaskName = "PDP One Deployment Agent Watchdog",
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
$deploymentAgentWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneDeploymentAgentHealthy.ps1"
$diskGuardScript = Join-Path $ProjectRoot "scripts\windows\Invoke-PDPOneDiskGuard.ps1"
if (-not (Test-Path -LiteralPath $startScript)) { throw "Stable startup script was not found." }
if (-not (Test-Path -LiteralPath $rancherStartupScript)) { throw "Resilient Rancher startup helper was not found." }
if (-not (Test-Path -LiteralPath $openScript)) { throw "Local web opener script was not found." }
if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }
if (-not (Test-Path -LiteralPath $deploymentAgentWatchdogScript)) { throw "Deployment Agent self-heal script was not found." }
if (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "Disk guard script was not found." }

# Recurring/headless maintenance must not attach a console window to the user's
# interactive desktop. S4U keeps the same Windows identity and elevation but
# runs the task non-interactively. The local-web opener deliberately remains
# Interactive because its purpose is to open the browser in the signed-in session.
$backgroundPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Highest
$interactivePrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

$startupArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
$startupAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $startupArguments
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
# Stable startup now allows one long initial Rancher/Docker wait plus one bounded
# rdctl shutdown/start recovery cycle. The 30-minute execution envelope prevents
# Task Scheduler from killing a legitimate slow Windows/WSL/Rancher boot.
$settings = New-ScheduledTaskSettingsSet -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $StartupTaskName -Action $startupAction -Trigger @($logonTrigger, $watchdogTrigger) -Principal $backgroundPrincipal -Settings $settings -Description "Starts PDP One after Windows logon and rechecks it every ten minutes. It tolerates slow Rancher startup, performs one bounded non-destructive Rancher recovery, preserves data and tokens, repairs Tailscale Funnel, and writes safe diagnostics on failure." -Force | Out-Null

# A NetworkProfile connection event gives PDP One an immediate second chance when
# Wi-Fi/Ethernet becomes connected after logon. /NP keeps this event task in the
# same passwordless non-interactive Task Scheduler model so it cannot flash a
# PowerShell console on the signed-in desktop.
$networkCommand = "powershell.exe $startupArguments"
$networkEventFilter = "*[System[Provider[@Name='Microsoft-Windows-NetworkProfile'] and EventID=10000]]"
& schtasks.exe /Create /TN $NetworkRecoveryTaskName /TR $networkCommand /SC ONEVENT /EC "Microsoft-Windows-NetworkProfile/Operational" /MO $networkEventFilter /RU $env:USERNAME /NP /RL HIGHEST /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The PDP One network-recovery Scheduled Task could not be registered."
}

# Begin health polling immediately at logon. Open-PDPOneLocal waits until local
# health is actually ready, so a fixed sleep only delays already-healthy boots.
# This one task remains Interactive because it intentionally opens the browser.
$openArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$openScript`" -TimeoutSeconds 300"
$openAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $openArguments
$openTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$openSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $OpenWebTaskName -Action $openAction -Trigger $openTrigger -Principal $interactivePrincipal -Settings $openSettings -Description "Begins polling PDP One local health immediately after logon and opens localhost on the first healthy response without changing Windows DNS." -Force | Out-Null

$mcpArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$mcpWatchdogScript`" -ProjectRoot `"$ProjectRoot`""
$mcpAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $mcpArguments
$mcpLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$mcpPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$mcpSettings = New-ScheduledTaskSettingsSet -RestartCount 6 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 6) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $backgroundPrincipal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs the MCP Docker image, verifies imports, recreates only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null

# The signed queue is useful only while the Windows Agent Scheduled Task is
# actually running. Supervise that fixed task independently of MCP/Rancher so a
# stopped or disabled Agent cannot leave valid signed requests stranded forever.
$agentRoot = "C:\ProgramData\PDP-One\deployment-agent"
try {
    $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
    $configuredAgentRoot = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT")
    if (-not [string]::IsNullOrWhiteSpace($configuredAgentRoot)) {
        $agentRoot = ($configuredAgentRoot -replace '/', '\')
    }
} catch { }
$deploymentAgentWatchdogArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$deploymentAgentWatchdogScript`" -AgentRoot `"$agentRoot`" -AgentTaskName `"PDP One Local Deployment Agent`""
$deploymentAgentWatchdogAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $deploymentAgentWatchdogArguments
$deploymentAgentWatchdogLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$deploymentAgentWatchdogPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$deploymentAgentWatchdogSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DeploymentAgentWatchdogTaskName -Action $deploymentAgentWatchdogAction -Trigger @($deploymentAgentWatchdogLogonTrigger, $deploymentAgentWatchdogPeriodicTrigger) -Principal $backgroundPrincipal -Settings $deploymentAgentWatchdogSettings -Description "Keeps only the fixed PDP One Local Deployment Agent Scheduled Task running. It never executes arbitrary commands and never interrupts a Running Agent." -Force | Out-Null

$diskGuardArguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$diskGuardScript`" -Mode scheduled -ProjectRoot `"$ProjectRoot`""
$diskGuardAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $diskGuardArguments
$diskGuardDailyTrigger = New-ScheduledTaskTrigger -Daily -At 3:15am
$diskGuardSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DiskGuardTaskName -Action $diskGuardAction -Trigger $diskGuardDailyTrigger -Principal $backgroundPrincipal -Settings $diskGuardSettings -Description "Maintains safe C drive capacity for PDP One. It prunes only unused build cache, images, stopped containers and networks, archives old restore-verified backups, compacts Rancher WSL VHDX only when needed, and never prunes Docker volumes." -Force | Out-Null

Write-Host "Scheduled Tasks '$StartupTaskName', '$NetworkRecoveryTaskName', '$OpenWebTaskName', '$McpWatchdogTaskName', '$DeploymentAgentWatchdogTaskName' and '$DiskGuardTaskName' are installed."
