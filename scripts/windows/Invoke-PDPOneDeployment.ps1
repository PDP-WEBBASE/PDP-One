#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$PreviewId,
    [Parameter(Mandatory = $true)][string]$AgentRoot,
    [string]$VerifiedBackupPath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
if (-not (Test-Path -LiteralPath $secretPath)) { throw "The one-time GitHub credential setup is incomplete." }
$secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null
$downloadDirectory = Join-Path $AgentRoot "downloads\$DeploymentId"
$extractDirectory = Join-Path $downloadDirectory "source"
if (Test-Path -LiteralPath $downloadDirectory) { Remove-Item -LiteralPath $downloadDirectory -Recurse -Force }
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $headers = @{ Authorization = "Bearer $plainToken"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "PDP-One-Local-Deployment-Agent" }
    $commit = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 60
    if ([string]$commit.sha -ne $CommitSha) { throw "GitHub did not return the approved exact commit." }
    New-Item -ItemType Directory -Force -Path $downloadDirectory | Out-Null
    $archive = Join-Path $downloadDirectory "approved-source.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$CommitSha" -Headers $headers -OutFile $archive -TimeoutSec 180
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
}

Expand-Archive -LiteralPath (Join-Path $downloadDirectory "approved-source.zip") -DestinationPath $extractDirectory -Force
$sourceRoot = Get-ChildItem -LiteralPath $extractDirectory -Directory | Select-Object -First 1
if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "docker-compose.yml"))) { throw "Approved source archive structure is invalid." }

$backupPath = ""
if ($VerifiedBackupPath) {
    $backupRoot = "C:\ProgramData\PDP-One\backups"
    if (-not (Test-Path -LiteralPath $backupRoot)) { throw "The verified backup root does not exist." }
    $resolvedRoot = (Resolve-Path -LiteralPath $backupRoot).Path.TrimEnd('\')
    $resolvedBackup = (Resolve-Path -LiteralPath $VerifiedBackupPath).Path.TrimEnd('\')
    if (-not $resolvedBackup.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Verified backup path is outside the protected backup root." }
    $backupReportPath = Join-Path $resolvedBackup "backup-report.json"
    if (-not (Test-Path -LiteralPath $backupReportPath)) { throw "Verified backup report is missing." }
    $backupReport = Get-Content -LiteralPath $backupReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not [bool]$backupReport.restore_verified) { throw "The supplied backup has not passed restore verification." }
    if ([string]$backupReport.approved_commit -ne $CommitSha) { throw "Verified backup commit does not match the approved deployment commit." }
    if ([string]$backupReport.deployment_id -ne $DeploymentId) { throw "Verified backup deployment identifier does not match." }
    $backupPath = $resolvedBackup
} else {
    # Fallback safety path for emergency/manual invocations. The normal signed
    # deployment flow supplies the fresh verified backup created before deploy.
    $backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneBackup.ps1") -Kind final -DeploymentId $DeploymentId -ApprovedCommit $CommitSha)
    if ($LASTEXITCODE -ne 0) { throw "Final backup creation failed. Deployment was not started." }
    $backupPath = [string]$backupOutput[-1]
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOneBackupRestore.ps1") -BackupPath $backupPath
    if ($LASTEXITCODE -ne 0) { throw "Final backup restore verification failed. Deployment was not started." }
}

$codeStage = Join-Path $downloadDirectory "previous-code"
New-Item -ItemType Directory -Force -Path $codeStage | Out-Null
& robocopy.exe $ProjectRoot $codeStage /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
if ($LASTEXITCODE -gt 7) { throw "Previous code snapshot could not be created." }
$codeArchive = Join-Path $backupPath "code-before-deployment.zip"
Compress-Archive -Path (Join-Path $codeStage "*") -DestinationPath $codeArchive -CompressionLevel Optimal -Force

$state = [ordered]@{
    deployment_id = $DeploymentId
    preview_id = $PreviewId
    approved_commit = $CommitSha
    backup_path = $backupPath
    code_archive = $codeArchive
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "updating"
}
$statePath = Join-Path $AgentRoot "state\last-deployment.json"
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Update-PDPOne.ps1") -SourceRoot $sourceRoot.FullName -InstalledRoot $ProjectRoot -ApprovedCommit $CommitSha -DeploymentId $DeploymentId -BackupPath $backupPath -CodeArchive $codeArchive -AgentAuthorized
if ($LASTEXITCODE -ne 0) {
    $state.status = "failed-or-rolled-back"
    $state.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    throw "Approved update failed. Automatic rollback was attempted by the updater."
}
$binRoot = Join-Path $AgentRoot "bin"
New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
Copy-Item -Path (Join-Path $ProjectRoot "scripts\windows\*.ps1") -Destination $binRoot -Force
Set-Content -LiteralPath (Join-Path $AgentRoot 'state\restart-agent-after-response') -Value ([DateTime]::UtcNow.ToString('o')) -Encoding ASCII
$state.status = "healthy"
$state.completed_at = (Get-Date).ToUniversalTime().ToString("o")
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
$reportPath = Join-Path $AgentRoot "reports\$DeploymentId.json"
$state | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8

# The rollback archive is stored inside the verified backup. The downloaded
# source ZIP, extracted source and uncompressed previous-code staging are no
# longer needed after a healthy deployment.
if (Test-Path -LiteralPath $downloadDirectory) { Remove-Item -LiteralPath $downloadDirectory -Recurse -Force }
Write-Output $reportPath
