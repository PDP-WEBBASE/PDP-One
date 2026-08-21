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
    stable_operational_interface_revision = "pdp-one.stable-bootstrap-control-plane.v1"
    agent_protocol_version = $null
    agent_sync_capable = $false
    agent_self_reconcile_capable = $false
    agent_bootstrap_manifest_hash = $null
    runtime_bootstrap_manifest_hash = $null
    agent_candidate_compatibility = "unknown"
    agent_migration_stage = $null
    status = "starting"
    error = $null
}

function Update-PDPOneAgentCapabilityMetadata {
    param([Parameter(Mandatory = $true)]$Report)
    try {
        $standardAgent = Join-Path $binRoot "Deployment-Agent.Standard.ps1"
        $deploymentWrapper = Join-Path $binRoot "Invoke-PDPOneDeployment.ps1"
        $reconcileHelper = Join-Path $binRoot "Invoke-PDPOneExactAgentReconciliation.ps1"
        if (Test-Path -LiteralPath $standardAgent) {
            $standardText = [IO.File]::ReadAllText($standardAgent, [Text.Encoding]::UTF8)
            $Report.agent_sync_capable = $standardText.Contains('"sync_agent_from_exact_commit" {')
        }
        if ((Test-Path -LiteralPath $deploymentWrapper) -and (Test-Path -LiteralPath $reconcileHelper)) {
            $wrapperText = [IO.File]::ReadAllText($deploymentWrapper, [Text.Encoding]::UTF8)
            $Report.agent_self_reconcile_capable = $wrapperText.Contains('Invoke-PDPOneExactAgentReconciliation.ps1')
        }

        $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
        $manifestPath = Join-Path $projectRoot "release\deployment-agent-compatibility.json"
        if (-not (Test-Path -LiteralPath $manifestPath)) {
            $Report.agent_candidate_compatibility = "manifest_unavailable"
            return
        }
        $manifestText = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8)
        $Report.runtime_bootstrap_manifest_hash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $manifest = $manifestText | ConvertFrom-Json
        if ([string]$manifest.schema -ne "pdp-one.deployment-agent-compatibility.v1" -or [int]$manifest.protocol_version -ne 1) {
            $Report.agent_candidate_compatibility = "unsupported_manifest"
            return
        }
        $migrationProperty = $manifest.PSObject.Properties["migration_stage"]
        $migrationStage = if ($null -ne $migrationProperty) { ([string]$migrationProperty.Value).Trim() } else { "" }
        if ($migrationStage) { $Report.agent_migration_stage = $migrationStage }

        $matches = $true
        foreach ($entry in @($manifest.bootstrap_files)) {
            $repositoryPath = [string]$entry.path
            $agentFile = [string]$entry.agent_file
            if ($repositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$' -or $agentFile -notmatch '^[A-Za-z0-9._-]+\.ps1$' -or $agentFile -ne (Split-Path $repositoryPath -Leaf)) {
                $matches = $false
                break
            }
            $sourcePath = Join-Path $projectRoot ($repositoryPath -replace '/', '\')
            $installedPath = Join-Path $binRoot $agentFile
            if (-not (Test-Path -LiteralPath $sourcePath) -or -not (Test-Path -LiteralPath $installedPath)) {
                $matches = $false
                break
            }
            $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
            $installedHash = (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not [string]::Equals($sourceHash, $installedHash, [StringComparison]::OrdinalIgnoreCase)) {
                $matches = $false
                break
            }
        }
        if ($matches) {
            $Report.agent_protocol_version = [int]$manifest.protocol_version
            $Report.agent_bootstrap_manifest_hash = [string]$Report.runtime_bootstrap_manifest_hash
            $Report.agent_candidate_compatibility = if ($migrationStage) { "migration_match" } else { "match" }
        } else {
            $Report.agent_candidate_compatibility = "drift"
        }
    } catch {
        $Report.agent_candidate_compatibility = "metadata_unavailable"
    }
}

try {
    if (-not (Test-Path -LiteralPath $agentScript)) {
        throw "The protected PDP One Deployment Agent wrapper is missing."
    }

    Update-PDPOneAgentCapabilityMetadata -Report $report

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