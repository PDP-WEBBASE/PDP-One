#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$PreviewId,
    [Parameter(Mandatory = $true)][string]$AgentRoot,
    [string]$VerifiedBackupPath = "",
    [switch]$DevelopmentFastMode
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

# Stable bootstrap control plane:
# The long-lived MCP tool keeps calling the same signed deploy_approved_release
# Agent action. The Agent-side wrapper itself inspects exact candidate
# compatibility and reconciles only manifest-declared protected scripts before
# any application deployment. A newly discovered MCP tool is never required.
$compatibilityScript = Join-Path $PSScriptRoot "Test-PDPOneExactCandidateCompatibility.ps1"
if (-not (Test-Path -LiteralPath $compatibilityScript)) {
    throw "The exact candidate compatibility preflight is missing."
}
$inspectionArguments = @(
    "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $compatibilityScript,
    "-CommitSha", $CommitSha,
    "-DeploymentId", $DeploymentId,
    "-AgentRoot", $AgentRoot,
    "-InspectionOnly"
)
$inspectionOutput = @(& powershell.exe @inspectionArguments)
if ($LASTEXITCODE -ne 0 -or $inspectionOutput.Count -eq 0) {
    throw "Exact candidate compatibility inspection failed before production deployment."
}
$inspectionReportPath = [string]$inspectionOutput[-1]
if ([string]::IsNullOrWhiteSpace($inspectionReportPath) -or -not (Test-Path -LiteralPath $inspectionReportPath)) {
    throw "Exact candidate compatibility inspection did not produce a readable report."
}
$inspection = Get-Content -LiteralPath $inspectionReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
$classification = ([string]$inspection.classification).Trim().ToUpperInvariant()

switch ($classification) {
    "MATCH" { }
    "SAFE_RECONCILABLE" {
        $reconciliationScript = Join-Path $PSScriptRoot "Invoke-PDPOneExactAgentReconciliation.ps1"
        if (-not (Test-Path -LiteralPath $reconciliationScript)) {
            throw "Exact Agent reconciliation is required but the fixed reconciliation helper is not installed. No production changes were made."
        }
        $reconciliationArguments = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $reconciliationScript,
            "-CommitSha", $CommitSha,
            "-DeploymentId", $DeploymentId,
            "-AgentRoot", $AgentRoot
        )
        $reconciliationOutput = @(& powershell.exe @reconciliationArguments)
        if ($LASTEXITCODE -ne 0 -or $reconciliationOutput.Count -eq 0) {
            throw "Exact Agent reconciliation failed before production deployment."
        }

        # Re-run the now-synchronized candidate preflight in strict mode. The
        # managed deployment also runs its own preflight; both must see MATCH.
        $strictOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $compatibilityScript -CommitSha $CommitSha -DeploymentId $DeploymentId -AgentRoot $AgentRoot)
        if ($LASTEXITCODE -ne 0 -or $strictOutput.Count -eq 0) {
            throw "Exact Agent reconciliation completed but strict compatibility verification did not reach MATCH. No production deployment was started."
        }
    }
    "PROTOCOL_MISMATCH" {
        throw "Exact candidate Agent protocol is incompatible. No production changes were made."
    }
    default {
        throw "Exact candidate Agent compatibility is unsafe. No production changes were made."
    }
}

# The managed wrapper delegates the exact-commit core to Invoke-PDPOneFastDeployment.ps1.
# It runs Invoke-PDPOneDiskGuard.ps1 with -Mode predeploy and -Mode postdeploy,
# but capacity is advisory and does not impose a fixed free-space deployment gate.
if ($DevelopmentFastMode) {
    $scriptPath = Join-Path $PSScriptRoot "Invoke-PDPOneManagedFastDeployment.ps1"
    $arguments = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath,
        "-CommitSha", $CommitSha,
        "-DeploymentId", $DeploymentId,
        "-PreviewId", $PreviewId,
        "-AgentRoot", $AgentRoot
    )
} else {
    $scriptPath = Join-Path $PSScriptRoot "Invoke-PDPOneDeployment.Standard.ps1"
    $arguments = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath,
        "-CommitSha", $CommitSha,
        "-DeploymentId", $DeploymentId,
        "-PreviewId", $PreviewId,
        "-AgentRoot", $AgentRoot,
        "-VerifiedBackupPath", $VerifiedBackupPath
    )
}

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "The selected deployment implementation is missing: $scriptPath"
}

& powershell.exe @arguments
exit $LASTEXITCODE