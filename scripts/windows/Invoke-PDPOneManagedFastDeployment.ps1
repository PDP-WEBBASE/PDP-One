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
. (Join-Path $PSScriptRoot "PDPOne.OperationLock.ps1")
$stateCompatibilityScript = Join-Path $PSScriptRoot "PDPOne.DeploymentStateCompatibility.ps1"
if (Test-Path -LiteralPath $stateCompatibilityScript) { . $stateCompatibilityScript }

$projectRoot = Get-PDPOneProjectRoot
$guardScript = Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1"
$policyScript = Join-Path $PSScriptRoot "Ensure-PDPOneRancherPolicy.ps1"
$compatibilityPreflightScript = Join-Path $PSScriptRoot "Test-PDPOneExactCandidateCompatibility.ps1"
$zeroDowntimeScript = Join-Path $PSScriptRoot "Invoke-PDPOneZeroDowntimeRegistryDeployment.ps1"
$scopedScript = Join-Path $PSScriptRoot "Invoke-PDPOneScopedRegistryDeployment.ps1"
$legacyScript = Join-Path $PSScriptRoot "Invoke-PDPOneRegistryFastDeployment.ps1"
if (Test-Path -LiteralPath $zeroDowntimeScript) {
    $innerScript = $zeroDowntimeScript
    $deploymentEngine = "zero_downtime_overlap_v1"
} elseif (Test-Path -LiteralPath $scopedScript) {
    $innerScript = $scopedScript
    $deploymentEngine = "scoped_release_manifest_v1"
} else {
    $innerScript = $legacyScript
    $deploymentEngine = "legacy_exact_sha"
}
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$deploymentOutput = @()
$deploymentExitCode = 1
$compatibilityPreflightReport = ""
$predeployGuardReport = ""
$postdeployGuardReport = ""
$rancherPolicyReport = ""
$deploymentLease = $null
$legacyStateUpgraded = $false
$startupTaskPolicyReconciled = $false

if (-not (Test-Path -LiteralPath $innerScript)) { throw "Registry-backed fast deployment implementation was not found." }

$deploymentLease = Enter-PDPOneDeploymentOperation -DeploymentId $DeploymentId -CommitSha $CommitSha -PreviewId $PreviewId -AgentRoot $AgentRoot
if ($null -eq $deploymentLease) { throw "Another PDP One deployment is already in progress." }

try {
    Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "deployment-compatibility-preflight"
    if (-not (Test-Path -LiteralPath $compatibilityPreflightScript)) { throw "Deployment compatibility preflight is missing from the installed Agent. Bootstrap the exact accepted preflight helper before retrying." }
    $preflightOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $compatibilityPreflightScript -CommitSha $CommitSha -DeploymentId $DeploymentId -AgentRoot $AgentRoot 2>&1)
    $preflightExitCode = $LASTEXITCODE
    if ($preflightExitCode -ne 0) {
        $preflightMessage = ConvertTo-PDPOneRedactedText (($preflightOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if ([string]::IsNullOrWhiteSpace($preflightMessage)) { $preflightMessage = "Deployment compatibility preflight failed without a diagnostic message." }
        $failureReportRoot = Join-Path $AgentRoot "reports"
        New-Item -ItemType Directory -Force -Path $failureReportRoot | Out-Null
        $failureReportPath = Join-Path $failureReportRoot ($DeploymentId + ".json")
        [ordered]@{
            schema="pdp-one.deployment-report.v3"; deployment_id=$DeploymentId; preview_id=$PreviewId; approved_commit=$CommitSha; previous_commit=""
            started_at=[DateTime]::UtcNow.ToString("o"); completed_at=[DateTime]::UtcNow.ToString("o"); status="failed"; stage="deployment-compatibility-preflight"
            change_management_mode="development_fast"; image_source="github_container_registry"; local_image_build_performed=$false; production_changed=$false
            health_profile="none"; changed_services=@(); changed_paths=@(); active_images=@{}; retained_previous_images=@{}
            connectivity_repair_attempted=$false; connectivity_repair_succeeded=$false; startup_task_policy_reconciled=$false; error=$preflightMessage
        } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $failureReportPath -Encoding UTF8
        throw "Deployment compatibility preflight failed before production changes. $preflightMessage"
    }
    if ($preflightOutput.Count -gt 0) { $compatibilityPreflightReport = [string]$preflightOutput[-1] }

    Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "applying-rancher-policy"
    if (Test-Path -LiteralPath $policyScript) {
        $policyOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $policyScript -DockerTimeoutSeconds 300)
        if ($LASTEXITCODE -ne 0) { throw "The Rancher Kubernetes-off policy could not be applied." }
        if ($policyOutput.Count -gt 0) { $rancherPolicyReport = [string]$policyOutput[-1] }
    }

    Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "predeploy-cleanup"
    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode predeploy -ProjectRoot $projectRoot -AgentRoot $AgentRoot -BuildCacheBudgetGB 2)
            if ($guardOutput.Count -gt 0) { $predeployGuardReport = [string]$guardOutput[-1] }
        } catch { Write-Warning "Pre-deployment cleanup could not finish. Registry deployment will still be attempted until Docker reports an actual write failure." }
    }

    if ($innerScript -eq $scopedScript -or $innerScript -eq $zeroDowntimeScript) {
        if (-not (Get-Command Update-PDPOneLegacyDeploymentStateForScopedEngine -ErrorAction SilentlyContinue)) { throw "Scoped deployment state-compatibility helper is missing." }
        $legacyStateUpgraded = [bool](Update-PDPOneLegacyDeploymentStateForScopedEngine -AgentRoot $AgentRoot)
    }

    Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "deploying-exact-commit"
    $deploymentOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $innerScript -CommitSha $CommitSha -DeploymentId $DeploymentId -PreviewId $PreviewId -AgentRoot $AgentRoot)
    $deploymentExitCode = $LASTEXITCODE

    if ($deploymentExitCode -eq 0) {
        Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "reconciling-startup-task-policy"
        $startupTaskPolicyScript = Join-Path $projectRoot "scripts\windows\Register-PDPOneStartupTask.ps1"
        if (-not (Test-Path -LiteralPath $startupTaskPolicyScript)) { throw "The exact deployed source is missing Register-PDPOneStartupTask.ps1." }
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $startupTaskPolicyScript -ProjectRoot $projectRoot -ApplyIfNeeded
        if ($LASTEXITCODE -ne 0) { throw "The exact deployed Windows Scheduled Task policy could not be reconciled." }
        $startupTaskPolicyReconciled = $true
    }
} finally {
    if ($null -ne $deploymentLease) { try { Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "postdeploy-cleanup" } catch { } }
    if (Test-Path -LiteralPath $downloadRoot) { try { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction Stop } catch { } }
    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode postdeploy -ProjectRoot $projectRoot -AgentRoot $AgentRoot -BuildCacheBudgetGB 2)
            if ($guardOutput.Count -gt 0) { $postdeployGuardReport = [string]$guardOutput[-1] }
        } catch { Write-Warning "Post-deployment cleanup did not finish. The deployment result is preserved and the daily disk task will retry cleanup." }
    }
    Exit-PDPOneDeploymentOperation -Lease $deploymentLease
    $deploymentLease = $null
}

if ($deploymentExitCode -ne 0) { foreach ($line in $deploymentOutput) { Write-Output $line }; exit $deploymentExitCode }

$deploymentReport = if ($deploymentOutput.Count -gt 0) { [string]$deploymentOutput[-1] } else { "" }
if ($deploymentReport -and (Test-Path -LiteralPath $deploymentReport)) {
    try {
        $report = Get-Content -LiteralPath $deploymentReport -Raw -Encoding UTF8 | ConvertFrom-Json
        $report | Add-Member -NotePropertyName compatibility_preflight_report -NotePropertyValue $compatibilityPreflightReport -Force
        $report | Add-Member -NotePropertyName compatibility_preflight_passed -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName rancher_policy_report -NotePropertyValue $rancherPolicyReport -Force
        $report | Add-Member -NotePropertyName predeploy_disk_guard_report -NotePropertyValue $predeployGuardReport -Force
        $report | Add-Member -NotePropertyName postdeploy_disk_guard_report -NotePropertyValue $postdeployGuardReport -Force
        $report | Add-Member -NotePropertyName deployment_operation_lock -NotePropertyValue "held_until_postdeploy_cleanup" -Force
        $report | Add-Member -NotePropertyName in_flight_commit_protected -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName competing_tasks_suppressed -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName obsolete_artifacts_cleaned_immediately -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName capacity_gate_enforced -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName deployment_attempted_until_actual_write_failure -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName local_image_build_performed -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName image_source -NotePropertyValue "github_container_registry" -Force
        $report | Add-Member -NotePropertyName deployment_engine -NotePropertyValue $deploymentEngine -Force
        $report | Add-Member -NotePropertyName legacy_state_upgraded_for_scoped_engine -NotePropertyValue $legacyStateUpgraded -Force
        $report | Add-Member -NotePropertyName startup_task_policy_reconciled -NotePropertyValue $startupTaskPolicyReconciled -Force
        $releaseManifestEngine = ($deploymentEngine -eq "scoped_release_manifest_v1" -or $deploymentEngine -eq "zero_downtime_overlap_v1")
        $retentionPolicy = if ($releaseManifestEngine) { "active_previous_and_inflight_release_manifests" } else { "active_previous_and_inflight_commit" }
        $report | Add-Member -NotePropertyName retained_image_policy -NotePropertyValue $retentionPolicy -Force
        $report | Add-Member -NotePropertyName kubernetes_enabled -NotePropertyValue $false -Force
        $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $deploymentReport -Encoding UTF8
    } catch { }
}
Write-Output $deploymentReport
