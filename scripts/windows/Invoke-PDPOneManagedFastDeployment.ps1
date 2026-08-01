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
$innerScript = Join-Path $PSScriptRoot "Invoke-PDPOneFastDeployment.ps1"
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$deploymentOutput = @()
$deploymentExitCode = 1
$predeployGuardReport = ""
$postdeployGuardReport = ""

if (-not (Test-Path -LiteralPath $innerScript)) {
    throw "Fast deployment implementation was not found."
}

try {
    if (Test-Path -LiteralPath $guardScript) {
        try {
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode predeploy -ProjectRoot $projectRoot)
            if ($guardOutput.Count -gt 0) { $predeployGuardReport = [string]$guardOutput[-1] }
        } catch {
            Write-Warning "Pre-deployment cleanup could not finish. Deployment will still be attempted until Docker reports an actual write failure."
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
            $guardOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $guardScript -Mode postdeploy -ProjectRoot $projectRoot)
            if ($guardOutput.Count -gt 0) { $postdeployGuardReport = [string]$guardOutput[-1] }
        } catch {
            Write-Warning "Post-deployment cleanup did not finish. The deployment result is preserved and the daily disk task will retry cleanup."
        }
    }
}

if ($deploymentExitCode -ne 0) {
    foreach ($line in $deploymentOutput) { Write-Output $line }
    exit $deploymentExitCode
}

$deploymentReport = if ($deploymentOutput.Count -gt 0) { [string]$deploymentOutput[-1] } else { "" }
if ($deploymentReport -and (Test-Path -LiteralPath $deploymentReport)) {
    try {
        $report = Get-Content -LiteralPath $deploymentReport -Raw -Encoding UTF8 | ConvertFrom-Json
        $report | Add-Member -NotePropertyName predeploy_disk_guard_report -NotePropertyValue $predeployGuardReport -Force
        $report | Add-Member -NotePropertyName postdeploy_disk_guard_report -NotePropertyValue $postdeployGuardReport -Force
        $report | Add-Member -NotePropertyName obsolete_artifacts_cleaned_immediately -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName capacity_gate_enforced -NotePropertyValue $false -Force
        $report | Add-Member -NotePropertyName deployment_attempted_until_actual_write_failure -NotePropertyValue $true -Force
        $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $deploymentReport -Encoding UTF8
    } catch { }
}

Write-Output $deploymentReport
