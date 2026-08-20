#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [string]$AgentTaskName = "PDP One Local Deployment Agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

if ($AgentTaskName -ne "PDP One Local Deployment Agent") {
    throw "Only the fixed PDP One Local Deployment Agent task may be supervised."
}

$binRoot = Join-Path $AgentRoot "bin"
$agentScript = Join-Path $binRoot "Deployment-Agent.ps1"
$reportRoot = Join-Path $AgentRoot "reports"
$incomingRoot = Join-Path $AgentRoot "queue\incoming"
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$reportPath = Join-Path $reportRoot "deployment-agent-watchdog.json"

$report = [ordered]@{
    schema = "pdp-one.deployment-agent-watchdog.v1"
    checked_at = [DateTime]::UtcNow.ToString("o")
    task_name = $AgentTaskName
    task_state_before = "unknown"
    task_state_after = "unknown"
    task_recreated = $false
    task_enabled = $false
    start_requested = $false
    incoming_requests = 0
    status = "starting"
    error = $null
}

try {
    if (-not (Test-Path -LiteralPath $agentScript)) {
        throw "The protected PDP One Deployment Agent wrapper is missing."
    }

    if (Test-Path -LiteralPath $incomingRoot) {
        $report.incoming_requests = @(Get-ChildItem -LiteralPath $incomingRoot -Filter "*.json" -File -ErrorAction SilentlyContinue).Count
    }

    $task = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        $arguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$agentScript`" -AgentRoot `"$AgentRoot`""
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew -StartWhenAvailable
        Register-ScheduledTask -TaskName $AgentTaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Processes only signed, allowlisted PDP One deployment and operational requests." -Force | Out-Null
        $report.task_recreated = $true
        $task = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    }

    $report.task_state_before = [string]$task.State
    if ([string]$task.State -eq "Disabled") {
        Enable-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop | Out-Null
        $report.task_enabled = $true
        $task = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    }

    # Never stop or restart a Running Agent here. A long exact deployment may
    # legitimately keep the worker busy. The watchdog only repairs missing,
    # disabled, Ready or otherwise non-running scheduler state.
    if ([string]$task.State -ne "Running") {
        Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
        $report.start_requested = $true
        Start-Sleep -Seconds 2
    }

    $after = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    $report.task_state_after = [string]$after.State
    if ([string]$after.State -ne "Running") {
        throw "The PDP One Deployment Agent Scheduled Task did not enter Running state."
    }

    $report.status = "healthy"
} catch {
    $report.status = "failed"
    $report.error = [string]$_.Exception.Message
} finally {
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $temporary = "$reportPath.tmp"
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $reportPath -Force
}

if ($report.status -ne "healthy") {
    Write-Error $report.error
    exit 1
}

Write-Output $reportPath
