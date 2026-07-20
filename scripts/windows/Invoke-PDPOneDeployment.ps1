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
$ProjectRoot = Get-PDPOneProjectRoot
$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
if (-not (Test-Path -LiteralPath $secretPath)) { throw "The one-time GitHub credential setup is incomplete." }
$secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null
$downloadDirectory = Join-Path $AgentRoot "downloads\$DeploymentId"
$extractDirectory = Join-Path $downloadDirectory "source"
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

# Mandatory gate: a fresh backup is created after approval and immediately
# restored into an isolated PostgreSQL container before any code is copied.
$backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneBackup.ps1") -Kind final -DeploymentId $DeploymentId -ApprovedCommit $CommitSha)
if ($LASTEXITCODE -ne 0) { throw "Final backup creation failed. Deployment was not started." }
$backupPath = [string]$backupOutput[-1]
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOneBackupRestore.ps1") -BackupPath $backupPath
if ($LASTEXITCODE -ne 0) { throw "Final backup restore verification failed. Deployment was not started." }

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
Write-Output $reportPath
