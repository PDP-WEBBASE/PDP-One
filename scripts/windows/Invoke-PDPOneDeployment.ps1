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
