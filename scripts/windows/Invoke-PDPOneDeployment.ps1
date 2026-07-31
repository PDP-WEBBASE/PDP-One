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
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Invoke-PDPOneAcquisitionRetry([string]$Stage, [scriptblock]$Action, [int]$Attempts = 3) {
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
        try {
            return & $Action
        } catch {
            $lastError = $_
            if ($attempt -ge $Attempts) { break }
            $delaySeconds = [Math]::Min(8, [int][Math]::Pow(2, $attempt))
            Start-Sleep -Seconds $delaySeconds
        }
    }
    $message = if ($null -ne $lastError) { ConvertTo-PDPOneRedactedText $lastError.Exception.Message } else { "Unknown acquisition error." }
    throw "$Stage failed after $Attempts attempts. $message"
}

$ProjectRoot = Get-PDPOneProjectRoot
$reportsRoot = Join-Path $AgentRoot "reports"
New-Item -ItemType Directory -Force -Path $reportsRoot | Out-Null
$reportPath = Join-Path $reportsRoot "$DeploymentId.json"
$attemptState = [ordered]@{
    deployment_id = $DeploymentId
    preview_id = $PreviewId
    approved_commit = $CommitSha
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    completed_at = $null
    status = "starting"
    stage = "initializing"
    error = $null
    backup_path = $null
    code_archive = $null
    production_changed = $false
    change_management_mode = $(if ($DevelopmentFastMode) { "development_fast" } else { "standard" })
    backup_skipped = [bool]$DevelopmentFastMode
}
$attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8

$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
$pointer = [IntPtr]::Zero
$plainToken = $null
$downloadDirectory = Join-Path $AgentRoot "downloads\$DeploymentId"
$extractDirectory = Join-Path $downloadDirectory "source"
$backupPath = ""

try {
    $attemptState.stage = "acquiring-approved-source"
    $attemptState.status = "running"
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8

    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The one-time GitHub credential setup is incomplete." }
    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The protected GitHub credential could not be opened in this Windows account." }

    if (Test-Path -LiteralPath $downloadDirectory) { Remove-Item -LiteralPath $downloadDirectory -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $downloadDirectory | Out-Null
    $archive = Join-Path $downloadDirectory "approved-source.zip"
    $headers = @{ Authorization = "Bearer $plainToken"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "PDP-One-Local-Deployment-Agent" }

    $commit = Invoke-PDPOneAcquisitionRetry "GitHub exact-commit verification" {
        Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 60
    }
    if ([string]$commit.sha -ne $CommitSha) { throw "GitHub did not return the approved exact commit." }

    Invoke-PDPOneAcquisitionRetry "GitHub approved-source download" {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
        Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$CommitSha" -Headers $headers -OutFile $archive -TimeoutSec 180
    } | Out-Null

    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -le 0) { throw "Approved source archive was not downloaded." }

    $attemptState.stage = "validating-approved-source"
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Expand-Archive -LiteralPath $archive -DestinationPath $extractDirectory -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractDirectory -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "docker-compose.yml"))) { throw "Approved source archive structure is invalid." }

    $attemptState.stage = $(if ($DevelopmentFastMode) { "preparing-code-only-rollback" } else { "validating-final-backup" })
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($DevelopmentFastMode) {
        $rollbackRoot = Join-Path $AgentRoot "rollback\$DeploymentId"
        if (Test-Path -LiteralPath $rollbackRoot) { Remove-Item -LiteralPath $rollbackRoot -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $rollbackRoot | Out-Null
        $backupPath = $rollbackRoot
        $attemptState.backup_path = $null
    } elseif ($VerifiedBackupPath) {
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
        $attemptState.backup_path = $backupPath
    } else {
        $backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneBackup.ps1") -Kind final -DeploymentId $DeploymentId -ApprovedCommit $CommitSha)
        if ($LASTEXITCODE -ne 0) { throw "Final backup creation failed. Deployment was not started." }
        $backupPath = [string]$backupOutput[-1]
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOneBackupRestore.ps1") -BackupPath $backupPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Final backup restore verification failed. Deployment was not started." }
        $attemptState.backup_path = $backupPath
    }
    $attemptState.stage = "snapshotting-current-code"
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $codeStage = Join-Path $downloadDirectory "previous-code"
    New-Item -ItemType Directory -Force -Path $codeStage | Out-Null
    & robocopy.exe $ProjectRoot $codeStage /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Previous code snapshot could not be created." }
    $codeArchive = Join-Path $backupPath "code-before-deployment.zip"
    Compress-Archive -Path (Join-Path $codeStage "*") -DestinationPath $codeArchive -CompressionLevel Optimal -Force
    $attemptState.code_archive = $codeArchive

    $state = [ordered]@{
        deployment_id = $DeploymentId
        preview_id = $PreviewId
        approved_commit = $CommitSha
        backup_path = $backupPath
        code_archive = $codeArchive
        started_at = $attemptState.started_at
        status = "updating"
        change_management_mode = $(if ($DevelopmentFastMode) { "development_fast" } else { "standard" })
    }
    $statePath = Join-Path $AgentRoot "state\last-deployment.json"
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

    $attemptState.stage = "updating-production"
    $attemptState.production_changed = $true
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $updateArgs = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "Update-PDPOne.ps1"),
        "-SourceRoot", $sourceRoot.FullName,
        "-InstalledRoot", $ProjectRoot,
        "-ApprovedCommit", $CommitSha,
        "-DeploymentId", $DeploymentId,
        "-BackupPath", $backupPath,
        "-CodeArchive", $codeArchive,
        "-AgentAuthorized"
    )
    if ($DevelopmentFastMode) { $updateArgs += "-DevelopmentFastMode" }
    & powershell.exe @updateArgs
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

    $attemptState.status = "healthy"
    $attemptState.stage = "completed"
    $attemptState.completed_at = $state.completed_at
    $attemptState.error = $null
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8

    if (Test-Path -LiteralPath $downloadDirectory) { Remove-Item -LiteralPath $downloadDirectory -Recurse -Force }
    Write-Output $reportPath
} catch {
    $attemptState.status = "failed"
    $attemptState.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    $attemptState.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    throw
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
}
