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

$diskGuardScript = Join-Path $PSScriptRoot "Invoke-PDPOneDiskGuard.ps1"
if (-not (Test-Path -LiteralPath $diskGuardScript)) { throw "The PDP One disk guard is missing." }
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $diskGuardScript -Mode predeploy
if ($LASTEXITCODE -ne 0) { throw "Deployment was blocked because C: free space is below the safe build threshold." }

if ($DevelopmentFastMode) {
    $scriptPath = Join-Path $PSScriptRoot "Invoke-PDPOneFastDeployment.ps1"
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
