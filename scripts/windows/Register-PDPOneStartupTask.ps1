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
    [string]$DiskGuardTaskName = "PDP One Disk Guard",
    [switch]$ApplyIfNeeded
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$taskPolicyVersion = "2026-08-21-hidden-background-tasks-v4"
$taskPolicyRoot = "C:\ProgramData\PDP-One\maintenance"
$taskPolicyPath = Join-Path $taskPolicyRoot "startup-task-policy.version"
if ($ApplyIfNeeded -and (Test-Path -LiteralPath $taskPolicyPath)) {
    $installedPolicyVersion = ([IO.File]::ReadAllText($taskPolicyPath)).Trim()
    if ($installedPolicyVersion -eq $taskPolicyVersion) {
        Write-Host "PDP One Scheduled Task policy is already current." -ForegroundColor DarkGreen
        return
    }
}

$startScript = Join-Path $ProjectRoot "scripts\windows\Start-PDPOne.ps1"
$rancherStartupScript = Join-Path $ProjectRoot "scripts\windows\Start-PDPOneRancherResilient.ps1"
$openScript = Join-Path $ProjectRoot "scripts\windows\Open-PDPOneLocal.ps1"
$mcpWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneMcpHealthy.ps1"
$deploymentAgentWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneDeploymentAgentHealthy.ps1"
$diskGuardScript = Join-Path $ProjectRoot "scripts\windows\Invoke-PDPOneDiskGuard.ps1"
$hiddenRunner = Join-Path $PSScriptRoot "Run-PDPOneHidden.vbs"
if (-not (Test-Path -LiteralPath $startScript)) { throw "Stable startup script was not found." }
if (-not (Test-Path -LiteralPath $rancherStartupScript)) { throw "Resilient Rancher startup helper was not found." }
if (-not (Test-Path -LiteralPath $openScript)) { throw "Local web opener script was not found." }
if (-not (Test-Path -LiteralPath $mcpWatchdogScript)) { throw "MCP self-heal script was not found." }
if (-not (Test-Path -LiteralPath $deploymentAgentWatchdogScript)) { throw "Deployment Agent self-heal script was not found." }
if (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "Disk guard script was not found." }
if (-not (Test-Path -LiteralPath $hiddenRunner)) { throw "Hidden scheduled-task launcher was not found." }

function ConvertTo-PDPOneTaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"')) { throw "Scheduled-task arguments may not contain a quote character." }
    return '"' + $Value + '"'
}

function New-PDPOneHiddenPowerShellAction {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$ScriptArguments = @()
    )
    $arguments = @("//B", "//NoLogo", (ConvertTo-PDPOneTaskArgument $hiddenRunner), (ConvertTo-PDPOneTaskArgument $ScriptPath))
    foreach ($argument in $ScriptArguments) {
        $arguments += ConvertTo-PDPOneTaskArgument ([string]$argument)
    }
    return New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot "System32\wscript.exe") -Argument ($arguments -join ' ')
}

# Keep the original Interactive principal and exact schedule semantics. The
# windowless WScript host only changes presentation: child PowerShell still runs
# under the same signed-in Windows identity and Highest run level, so Rancher,
# DPAPI/user profile access and existing local resource permissions are preserved.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

$startupAction = New-PDPOneHiddenPowerShellAction -ScriptPath $startScript
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
# Stable startup now allows one long initial Rancher/Docker wait plus one bounded
# rdctl shutdown/start recovery cycle. The 30-minute execution envelope prevents
# Task Scheduler from killing a legitimate slow Windows/WSL/Rancher boot.
$settings = New-ScheduledTaskSettingsSet -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $StartupTaskName -Action $startupAction -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings -Description "Starts PDP One after Windows logon and rechecks it every ten minutes. It tolerates slow Rancher startup, performs one bounded non-destructive Rancher recovery, preserves data and tokens, repairs Tailscale Funnel, and writes safe diagnostics on failure." -Force | Out-Null

# A NetworkProfile connection event gives PDP One an immediate second chance when
# Wi-Fi/Ethernet becomes connected after logon. Keep its existing interactive
# security context, but route PowerShell through the same windowless host.
$networkRunner = ConvertTo-PDPOneTaskArgument $hiddenRunner
$networkStartScript = ConvertTo-PDPOneTaskArgument $startScript
$networkCommand = "`"$env:SystemRoot\System32\wscript.exe`" //B //NoLogo $networkRunner $networkStartScript"
$networkEventFilter = "*[System[Provider[@Name='Microsoft-Windows-NetworkProfile'] and EventID=10000]]"
& schtasks.exe /Create /TN $NetworkRecoveryTaskName /TR $networkCommand /SC ONEVENT /EC "Microsoft-Windows-NetworkProfile/Operational" /MO $networkEventFilter /RL HIGHEST /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The PDP One network-recovery Scheduled Task could not be registered."
}

# Begin health polling immediately at logon. Open-PDPOneLocal waits until local
# health is actually ready, so a fixed sleep only delays already-healthy boots.
$openAction = New-PDPOneHiddenPowerShellAction -ScriptPath $openScript -ScriptArguments @("-TimeoutSeconds", "300")
$openTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$openSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $OpenWebTaskName -Action $openAction -Trigger $openTrigger -Principal $principal -Settings $openSettings -Description "Begins polling PDP One local health immediately after logon and opens localhost on the first healthy response without changing Windows DNS." -Force | Out-Null

$mcpAction = New-PDPOneHiddenPowerShellAction -ScriptPath $mcpWatchdogScript -ScriptArguments @("-ProjectRoot", $ProjectRoot)
$mcpLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$mcpPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$mcpSettings = New-ScheduledTaskSettingsSet -RestartCount 6 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 6) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $principal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs the MCP Docker image, verifies imports, recreates only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null

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
$deploymentAgentWatchdogAction = New-PDPOneHiddenPowerShellAction -ScriptPath $deploymentAgentWatchdogScript -ScriptArguments @("-AgentRoot", $agentRoot, "-AgentTaskName", "PDP One Local Deployment Agent")
$deploymentAgentWatchdogLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$deploymentAgentWatchdogPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$deploymentAgentWatchdogSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DeploymentAgentWatchdogTaskName -Action $deploymentAgentWatchdogAction -Trigger @($deploymentAgentWatchdogLogonTrigger, $deploymentAgentWatchdogPeriodicTrigger) -Principal $principal -Settings $deploymentAgentWatchdogSettings -Description "Keeps only the fixed PDP One Local Deployment Agent Scheduled Task running. It never executes arbitrary commands and never interrupts a Running Agent." -Force | Out-Null

$diskGuardAction = New-PDPOneHiddenPowerShellAction -ScriptPath $diskGuardScript -ScriptArguments @("-Mode", "scheduled", "-ProjectRoot", $ProjectRoot)
$diskGuardDailyTrigger = New-ScheduledTaskTrigger -Daily -At 3:15am
$diskGuardSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DiskGuardTaskName -Action $diskGuardAction -Trigger $diskGuardDailyTrigger -Principal $principal -Settings $diskGuardSettings -Description "Maintains safe C drive capacity for PDP One. It prunes only unused build cache, images, stopped containers and networks, archives old restore-verified backups, compacts Rancher WSL VHDX only when needed, and never prunes Docker volumes." -Force | Out-Null

New-Item -ItemType Directory -Force -Path $taskPolicyRoot | Out-Null
[IO.File]::WriteAllText($taskPolicyPath, $taskPolicyVersion, [Text.UTF8Encoding]::new($false))
Write-Host "Scheduled Tasks '$StartupTaskName', '$NetworkRecoveryTaskName', '$OpenWebTaskName', '$McpWatchdogTaskName', '$DeploymentAgentWatchdogTaskName' and '$DiskGuardTaskName' are installed." -ForegroundColor Green
