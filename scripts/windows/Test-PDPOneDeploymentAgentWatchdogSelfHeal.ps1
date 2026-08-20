#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [string]$AgentTaskName = "PDP One Local Deployment Agent",
    [string]$WatchdogTaskName = "PDP One Deployment Agent Watchdog",
    [string]$SelfTestTaskName = "PDP One Deployment Agent Watchdog Self Test",
    [int]$MaxWaitSeconds = 120
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

if ($AgentTaskName -ne "PDP One Local Deployment Agent") {
    throw "Only the fixed PDP One Local Deployment Agent task may be tested."
}
if ($WatchdogTaskName -ne "PDP One Deployment Agent Watchdog") {
    throw "Only the fixed PDP One Deployment Agent Watchdog task may be used."
}
if ($SelfTestTaskName -ne "PDP One Deployment Agent Watchdog Self Test") {
    throw "Only the fixed PDP One watchdog self-test task may be used."
}

$reportsRoot = Join-Path $AgentRoot "reports"
$stateRoot = Join-Path $AgentRoot "state"
$incomingRoot = Join-Path $AgentRoot "queue\incoming"
$deploymentStatePath = Join-Path $stateRoot "deployment-in-progress.json"
$reportPath = Join-Path $reportsRoot "deployment-agent-watchdog-selftest.json"
$acceptanceMarkerPath = Join-Path $stateRoot "deployment-agent-watchdog-selftest-v1.accepted"
New-Item -ItemType Directory -Force -Path $reportsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

$report = [ordered]@{
    schema = "pdp-one.deployment-agent-watchdog-selftest.v1"
    started_at = [DateTime]::UtcNow.ToString("o")
    completed_at = $null
    status = "starting"
    agent_task_name = $AgentTaskName
    watchdog_task_name = $WatchdogTaskName
    lane_wait_seconds = 0
    agent_state_before = "unknown"
    agent_stop_requested = $false
    stopped_at = $null
    recovered_by_watchdog = $false
    recovery_seconds = $null
    agent_state_after = "unknown"
    safety_fallback_started = $false
    error = $null
}

function Write-SelfTestReport {
    $temporary = "$reportPath.tmp"
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $reportPath -Force
}

function Test-DeploymentLaneIdle {
    if (Test-Path -LiteralPath $deploymentStatePath) {
        try {
            $state = Get-Content -LiteralPath $deploymentStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $expiresProperty = $state.PSObject.Properties["expires_at"]
            if ($null -eq $expiresProperty -or [string]::IsNullOrWhiteSpace([string]$expiresProperty.Value)) {
                return $false
            }
            $expires = [DateTimeOffset]::Parse([string]$expiresProperty.Value)
            if ($expires -gt [DateTimeOffset]::UtcNow) { return $false }
        } catch {
            return $false
        }
    }
    if (Test-Path -LiteralPath $incomingRoot) {
        if (@(Get-ChildItem -LiteralPath $incomingRoot -Filter "*.json" -File -ErrorAction SilentlyContinue).Count -gt 0) {
            return $false
        }
    }
    return $true
}

try {
    $watchdogTask = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
    if ($null -eq $watchdogTask) { throw "The fixed Deployment Agent watchdog Scheduled Task is missing." }
    if ([string]$watchdogTask.State -eq "Disabled") { throw "The fixed Deployment Agent watchdog Scheduled Task is disabled." }

    $laneDeadline = (Get-Date).AddSeconds([Math]::Max(60, $MaxWaitSeconds))
    while ((Get-Date) -lt $laneDeadline -and -not (Test-DeploymentLaneIdle)) {
        Start-Sleep -Seconds 5
        $report.lane_wait_seconds = [int]$report.lane_wait_seconds + 5
    }
    if (-not (Test-DeploymentLaneIdle)) {
        throw "The deployment lane did not become idle; the watchdog self-test made no Agent state change."
    }

    $agentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
    if ($null -eq $agentTask) { throw "The fixed PDP One Local Deployment Agent Scheduled Task is missing." }

    # If the Agent is not currently Running, give the periodic watchdog one normal
    # interval to establish the baseline before deliberately testing recovery.
    $baselineDeadline = (Get-Date).AddSeconds(90)
    while ([string]$agentTask.State -ne "Running" -and (Get-Date) -lt $baselineDeadline) {
        Start-Sleep -Seconds 3
        $agentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    }
    if ([string]$agentTask.State -ne "Running") {
        throw "The Agent was not Running before the self-test, so a controlled stop was not attempted."
    }

    $report.agent_state_before = [string]$agentTask.State
    Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    $report.agent_stop_requested = $true
    $report.stopped_at = [DateTime]::UtcNow.ToString("o")

    $stopDeadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 500
        $agentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    } while ([string]$agentTask.State -eq "Running" -and (Get-Date) -lt $stopDeadline)
    if ([string]$agentTask.State -eq "Running") {
        throw "The controlled Agent stop did not complete; recovery was not tested."
    }

    $recoveryStarted = Get-Date
    $recoveryDeadline = $recoveryStarted.AddSeconds([Math]::Max(75, $MaxWaitSeconds))
    do {
        Start-Sleep -Seconds 2
        $agentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
        if ([string]$agentTask.State -eq "Running") { break }
    } while ((Get-Date) -lt $recoveryDeadline)

    if ([string]$agentTask.State -ne "Running") {
        $report.safety_fallback_started = $true
        Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
        Start-Sleep -Seconds 3
        $agentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
        throw "The periodic watchdog did not restore the Agent within the bounded window; a direct fixed-task safety restart was requested."
    }

    $report.recovered_by_watchdog = $true
    $report.recovery_seconds = [int][Math]::Ceiling(((Get-Date) - $recoveryStarted).TotalSeconds)
    $report.agent_state_after = [string]$agentTask.State
    $report.status = "healthy"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    [IO.File]::WriteAllText($acceptanceMarkerPath, $report.completed_at, [Text.UTF8Encoding]::new($false))
    Write-SelfTestReport
    Write-Output $reportPath
} catch {
    $report.status = "failed"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = [string]$_.Exception.Message
    try {
        $after = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
        if ($null -ne $after -and [string]$after.State -ne "Running") {
            $report.safety_fallback_started = $true
            Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            $after = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
        }
        if ($null -ne $after) { $report.agent_state_after = [string]$after.State }
    } catch { }
    Write-SelfTestReport
    Write-Error $report.error
    exit 1
} finally {
    try {
        Unregister-ScheduledTask -TaskName $SelfTestTaskName -Confirm:$false -ErrorAction SilentlyContinue
    } catch { }
}
