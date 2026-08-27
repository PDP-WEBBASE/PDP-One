#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$StartupTaskName = "PDP One Stable Startup",
    [string]$NetworkRecoveryTaskName = "PDP One Network Recovery",
    [string]$OpenWebTaskName = "PDP One Open Local Web",
    [string]$McpWatchdogTaskName = "PDP One MCP Self Heal",
    [string]$McpObservabilityTaskName = "PDP One MCP Route Observability",
    [string]$DeploymentAgentWatchdogTaskName = "PDP One Deployment Agent Watchdog",
    [string]$DiskGuardTaskName = "PDP One Disk Guard",
    [switch]$ApplyIfNeeded
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.HiddenTask.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$taskPolicyVersion = "2026-08-27-passive-mcp-route-observability-v6"
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
$mcpObservabilityScript = Join-Path $ProjectRoot "scripts\windows\Observe-PDPOneMcpRoute.ps1"
$deploymentAgentWatchdogScript = Join-Path $ProjectRoot "scripts\windows\Ensure-PDPOneDeploymentAgentHealthy.ps1"
$diskGuardScript = Join-Path $ProjectRoot "scripts\windows\Invoke-PDPOneDiskGuard.ps1"
$hiddenRunner = Get-PDPOneHiddenRunnerPath -BaseDirectory $PSScriptRoot
foreach ($required in @($startScript, $rancherStartupScript, $openScript, $mcpWatchdogScript, $mcpObservabilityScript, $deploymentAgentWatchdogScript, $diskGuardScript, $hiddenRunner)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required Scheduled Task source was not found: $(Split-Path $required -Leaf)" }
}

# Keep the original Interactive principal and exact schedule semantics. WScript
# changes only presentation; PowerShell runs under the same signed-in identity
# and Highest run level, preserving Rancher, DPAPI and local resource access.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

$startupAction = New-PDPOneHiddenPowerShellAction -ScriptPath $startScript -HiddenRunnerPath $hiddenRunner
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $StartupTaskName -Action $startupAction -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings -Description "Starts PDP One after Windows logon and rechecks it every ten minutes. It tolerates slow Rancher startup, performs one bounded non-destructive Rancher recovery, preserves data and tokens, repairs Tailscale Funnel, and writes safe diagnostics on failure." -Force | Out-Null

$networkRunner = ConvertTo-PDPOneScheduledTaskArgument $hiddenRunner
$networkStartScript = ConvertTo-PDPOneScheduledTaskArgument $startScript
$networkCommand = "`"$env:SystemRoot\System32\wscript.exe`" //B //NoLogo $networkRunner $networkStartScript"
$networkEventFilter = "*[System[Provider[@Name='Microsoft-Windows-NetworkProfile'] and EventID=10000]]"
& schtasks.exe /Create /TN $NetworkRecoveryTaskName /TR $networkCommand /SC ONEVENT /EC "Microsoft-Windows-NetworkProfile/Operational" /MO $networkEventFilter /RL HIGHEST /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The PDP One network-recovery Scheduled Task could not be registered." }

$openAction = New-PDPOneHiddenPowerShellAction -ScriptPath $openScript -ScriptArguments @("-TimeoutSeconds", "300") -HiddenRunnerPath $hiddenRunner
$openTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$openSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $OpenWebTaskName -Action $openAction -Trigger $openTrigger -Principal $principal -Settings $openSettings -Description "Begins polling PDP One local health immediately after logon and opens localhost on the first healthy response without changing Windows DNS." -Force | Out-Null

$mcpAction = New-PDPOneHiddenPowerShellAction -ScriptPath $mcpWatchdogScript -ScriptArguments @("-ProjectRoot", $ProjectRoot) -HiddenRunnerPath $hiddenRunner
$mcpLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$mcpPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$mcpSettings = New-ScheduledTaskSettingsSet -RestartCount 6 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 6) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $McpWatchdogTaskName -Action $mcpAction -Trigger @($mcpLogonTrigger, $mcpPeriodicTrigger) -Principal $principal -Settings $mcpSettings -Description "Checks the PDP One MCP container every five minutes. If it is missing or restarting, it repairs only MCP, preserves tokens and never touches Docker volumes or PostgreSQL data." -Force | Out-Null

$mcpObservabilityAction = New-PDPOneHiddenPowerShellAction -ScriptPath $mcpObservabilityScript -ScriptArguments @("-ProjectRoot", $ProjectRoot) -HiddenRunnerPath $hiddenRunner
$mcpObservabilityLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$mcpObservabilityPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$mcpObservabilitySettings = New-ScheduledTaskSettingsSet -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 45) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $McpObservabilityTaskName -Action $mcpObservabilityAction -Trigger @($mcpObservabilityLogonTrigger, $mcpObservabilityPeriodicTrigger) -Principal $principal -Settings $mcpObservabilitySettings -Description "Records passive MCP route checkpoints once per minute for later root-cause analysis. It never restarts services, repairs routes, rotates tokens, changes Docker volumes, or queries business data." -Force | Out-Null

$agentRoot = "C:\ProgramData\PDP-One\deployment-agent"
try {
    $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
    $configuredAgentRoot = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT")
    if (-not [string]::IsNullOrWhiteSpace($configuredAgentRoot)) { $agentRoot = ($configuredAgentRoot -replace '/', '\') }
} catch { }
$deploymentAgentWatchdogAction = New-PDPOneHiddenPowerShellAction -ScriptPath $deploymentAgentWatchdogScript -ScriptArguments @("-AgentRoot", $agentRoot, "-AgentTaskName", "PDP One Local Deployment Agent") -HiddenRunnerPath $hiddenRunner
$deploymentAgentWatchdogLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$deploymentAgentWatchdogPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$deploymentAgentWatchdogSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DeploymentAgentWatchdogTaskName -Action $deploymentAgentWatchdogAction -Trigger @($deploymentAgentWatchdogLogonTrigger, $deploymentAgentWatchdogPeriodicTrigger) -Principal $principal -Settings $deploymentAgentWatchdogSettings -Description "Keeps only the fixed PDP One Local Deployment Agent Scheduled Task running. It never executes arbitrary commands and never interrupts a Running Agent." -Force | Out-Null

$diskGuardAction = New-PDPOneHiddenPowerShellAction -ScriptPath $diskGuardScript -ScriptArguments @("-Mode", "scheduled", "-ProjectRoot", $ProjectRoot) -HiddenRunnerPath $hiddenRunner
$diskGuardDailyTrigger = New-ScheduledTaskTrigger -Daily -At 3:15am
$diskGuardSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $DiskGuardTaskName -Action $diskGuardAction -Trigger $diskGuardDailyTrigger -Principal $principal -Settings $diskGuardSettings -Description "Maintains safe C drive capacity for PDP One. It prunes only unused build cache, images, stopped containers and networks, archives old restore-verified backups, compacts Rancher WSL VHDX only when needed, and never prunes Docker volumes." -Force | Out-Null

foreach ($taskName in @($StartupTaskName, $NetworkRecoveryTaskName, $OpenWebTaskName, $McpWatchdogTaskName, $McpObservabilityTaskName, $DeploymentAgentWatchdogTaskName, $DiskGuardTaskName)) {
    Assert-PDPOneScheduledTaskWindowless -TaskName $taskName -HiddenRunnerPath $hiddenRunner | Out-Null
}

New-Item -ItemType Directory -Force -Path $taskPolicyRoot | Out-Null
[IO.File]::WriteAllText($taskPolicyPath, $taskPolicyVersion, [Text.UTF8Encoding]::new($false))
Write-Host "PDP One recurring Windows Scheduled Tasks are installed with the windowless launcher." -ForegroundColor Green
