#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$PreviewId,
    [Parameter(Mandatory = $true)][string]$AgentRoot
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$projectRoot = Get-PDPOneProjectRoot
$guardScript = Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1"
$policyScript = Join-Path $PSScriptRoot "Ensure-PDPOneRancherPolicy.ps1"
$innerScript = Join-Path $PSScriptRoot "Invoke-PDPOneRegistryFastDeployment.ps1"
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$stateRoot = Join-Path $AgentRoot "state"
$coordinationMarker = Join-Path $stateRoot "deployment-in-progress.json"
$coordinationToken = [Guid]::NewGuid().ToString("N")
$coordinationMutex = New-Object Threading.Mutex($false, "Global\PDP-One-Deployment-Coordinator")
$coordinationMutexHeld = $false
$script:taskStates = @()
$deploymentOutput = @()
$deploymentExitCode = 1
$predeployGuardReport = ""
$postdeployGuardReport = ""
$rancherPolicyReport = ""

$coordinatedTaskNames = @(
    "PDP One Stable Startup",
    "PDP One Open Local Web",
    "PDP One MCP Self Heal",
    "PDP One Disk Guard",
    "PDP One Emergency Disk Guard"
)

function Suspend-PDPOneCompetingTasks {
    foreach ($taskName in $coordinatedTaskNames) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) { continue }

        $wasEnabled = ([string]$task.State -ne "Disabled")
        $script:taskStates += [pscustomobject]@{
            Name = $taskName
            WasEnabled = $wasEnabled
        }

        try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch { }
        if ($wasEnabled) {
            Disable-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
        }
    }
}

function Restore-PDPOneCompetingTasks {
    foreach ($taskState in $script:taskStates) {
        if (-not [bool]$taskState.WasEnabled) { continue }
        try {
            Enable-ScheduledTask -TaskName ([string]$taskState.Name) -ErrorAction Stop | Out-Null
        } catch {
            Write-Warning ("Scheduled task could not be restored: " + [string]$taskState.Name)
        }
    }
}

function Remove-PDPOneCoordinationMarker {
    if (-not (Test-Path -LiteralPath $coordinationMarker)) { return }
    try {
        $marker = Get-Content -LiteralPath $coordinationMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$marker.coordination_token -ne $coordinationToken) { return }
    } catch {
        Remove-Item -LiteralPath $coordinationMarker -Force -ErrorAction SilentlyContinue
        return
    }
    Remove-Item -LiteralPath $coordinationMarker -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $innerScript)) {
    throw "Registry-backed fast deployment implementation was not found."
}

try {
    $coordinationMutexHeld = $coordinationMutex.WaitOne(0)
    if (-not $coordinationMutexHeld) {
        throw "Another coordinated PDP One deployment is already active."
    }

    New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
    [ordered]@{
        deployment_id = $DeploymentId
        preview_id = $PreviewId
        commit_sha = $CommitSha
        coordination_token = $coordinationToken
        process_id = $PID
        started_at = [DateTime]::UtcNow.ToString("o")
        status = "in_progress"
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $coordinationMarker -Encoding UTF8

    Suspend-PDPOneCompetingTasks

    if (Test-Path -LiteralPath $policyScript) {
        $policyOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $policyScript -DockerTimeoutSeconds 300)
        if ($LASTEXITCODE -ne 0) { throw "The Rancher Kubernetes-off policy could not be applied." }
        if ($policyOutput.Count -gt 0) { $rancherPolicyReport = [string]$policyOutput[-1] }
    }

    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode predeploy -ProjectRoot $projectRoot -BuildCacheBudgetGB 2)
            if ($guardOutput.Count -gt 0) { $predeployGuardReport = [string]$guardOutput[-1] }
        } catch {
            Write-Warning "Pre-deployment cleanup could not finish. Registry deployment will still be attempted until Docker reports an actual write failure."
        }
    }

    $deploymentOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $innerScript -CommitSha $CommitSha -DeploymentId $DeploymentId -PreviewId $PreviewId -AgentRoot $AgentRoot)
    $deploymentExitCode = $LASTEXITCODE
} finally {
    if (Test-Path -LiteralPath $downloadRoot) {
        try { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction Stop } catch { }
    }

    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode postdeploy -ProjectRoot $projectRoot -BuildCacheBudgetGB 2)
            if ($guardOutput.Count -gt 0) { $postdeployGuardReport = [string]$guardOutput[-1] }
        } catch {
            Write-Warning "Post-deployment cleanup did not finish. The deployment result is preserved and the daily disk task will retry cleanup."
        }
    }

    Remove-PDPOneCoordinationMarker
    Restore-PDPOneCompetingTasks

    if ($coordinationMutexHeld) {
        $coordinationMutex.ReleaseMutex()
    }
    $coordinationMutex.Dispose()
}

if ($deploymentExitCode -ne 0) {
    foreach ($line in $deploymentOutput) { Write-Output $line }
    exit $deploymentExitCode
}

$deploymentReport = if ($deploymentOutput.Count -gt 0) { [string]$deploymentOutput[-1] } else { "" }
if ($deploymentReport -and (Test-Path -LiteralPath $deploymentReport)) {
    try {
        $report = Get-Content -LiteralPath $deploymentReport -Raw -Encoding UTF8 | ConvertFrom-Json
        $report | Add-Member -NotePropertyName rancher_policy_report -NotePropertyValue $rancherPolicyReport -Force
        $report | Add-Member -NotePropertyName predeploy_disk_guard_report -NotePropertyValue $predeployGuardReport -Force
        $report | Add-Member -NotePropertyName postdeploy_disk_guard_report -NotePropertyValue $postdeployGuardReport -Force
        $report | Add-Member -NotePropertyName deployment_coordination_lock -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName competing_tasks_suspended -NotePropertyValue @($script:taskStates | ForEach-Object { $_.Name }) -Force
        $report | Add-Member -NotePropertyName obsolete_artifacts_cleaned_immediately -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName capacity_gate_enforced -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName deployment_attempted_until_actual_write_failure -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName local_image_build_performed -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName image_source -NotePropertyValue "github_container_registry" -Force
        $report | Add-Member -NotePropertyName retained_image_policy -NotePropertyValue "active_commit_and_previous_commit" -Force
        $report | Add-Member -NotePropertyName kubernetes_enabled -NotePropertyValue $false -Force
        $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $deploymentReport -Encoding UTF8
    } catch { }
}

Write-Output $deploymentReport
