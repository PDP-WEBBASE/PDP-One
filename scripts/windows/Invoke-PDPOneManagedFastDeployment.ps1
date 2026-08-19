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

$projectRoot = Get-PDPOneProjectRoot
$guardScript = Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1"
$policyScript = Join-Path $PSScriptRoot "Ensure-PDPOneRancherPolicy.ps1"
$scopedScript = Join-Path $PSScriptRoot "Invoke-PDPOneScopedRegistryDeployment.ps1"
$legacyScript = Join-Path $PSScriptRoot "Invoke-PDPOneRegistryFastDeployment.ps1"
$innerScript = if (Test-Path -LiteralPath $scopedScript) { $scopedScript } else { $legacyScript }
$deploymentEngine = if ($innerScript -eq $scopedScript) { "scoped_release_manifest_v1" } else { "legacy_exact_sha" }
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$deploymentOutput = @()
$deploymentExitCode = 1
$predeployGuardReport = ""
$postdeployGuardReport = ""
$rancherPolicyReport = ""
$deploymentLease = $null

if (-not (Test-Path -LiteralPath $innerScript)) {
    throw "Registry-backed fast deployment implementation was not found."
}

$deploymentLease = Enter-PDPOneDeploymentOperation `
    -DeploymentId $DeploymentId `
    -CommitSha $CommitSha `
    -PreviewId $PreviewId `
    -AgentRoot $AgentRoot

if ($null -eq $deploymentLease) {
    throw "Another PDP One deployment is already in progress."
}

try {
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
        } catch {
            Write-Warning "Pre-deployment cleanup could not finish. Registry deployment will still be attempted until Docker reports an actual write failure."
        }
    }

    # Keep this stable stage name for existing deployment-operation observers and
    # contracts. The selected engine may activate an exact release manifest.
    Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "deploying-exact-commit"
    $deploymentOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $innerScript -CommitSha $CommitSha -DeploymentId $DeploymentId -PreviewId $PreviewId -AgentRoot $AgentRoot)
    $deploymentExitCode = $LASTEXITCODE
} finally {
    if ($null -ne $deploymentLease) {
        try { Write-PDPOneDeploymentOperation -Lease $deploymentLease -Stage "postdeploy-cleanup" } catch { }
    }

    if (Test-Path -LiteralPath $downloadRoot) {
        try { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction Stop } catch { }
    }

    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode postdeploy -ProjectRoot $projectRoot -AgentRoot $AgentRoot -BuildCacheBudgetGB 2)
            if ($guardOutput.Count -gt 0) { $postdeployGuardReport = [string]$guardOutput[-1] }
        } catch {
            Write-Warning "Post-deployment cleanup did not finish. The deployment result is preserved and the daily disk task will retry cleanup."
        }
    }

    Exit-PDPOneDeploymentOperation -Lease $deploymentLease
    $deploymentLease = $null
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
        $report | Add-Member -NotePropertyName deployment_operation_lock -NotePropertyValue "held_until_postdeploy_cleanup" -Force
        $report | Add-Member -NotePropertyName in_flight_commit_protected -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName competing_tasks_suppressed -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName obsolete_artifacts_cleaned_immediately -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName capacity_gate_enforced -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName deployment_attempted_until_actual_write_failure -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName local_image_build_performed -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName image_source -NotePropertyValue "github_container_registry" -Force
        $report | Add-Member -NotePropertyName deployment_engine -NotePropertyValue $deploymentEngine -Force
        $retentionPolicy = if ($deploymentEngine -eq "scoped_release_manifest_v1") { "active_previous_and_inflight_release_manifests" } else { "active_previous_and_inflight_commit" }
        $report | Add-Member -NotePropertyName retained_image_policy -NotePropertyValue $retentionPolicy -Force
        $report | Add-Member -NotePropertyName kubernetes_enabled -NotePropertyValue $false -Force
        $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $deploymentReport -Encoding UTF8
    } catch { }
}

Write-Output $deploymentReport
