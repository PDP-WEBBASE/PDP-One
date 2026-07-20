#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$PortableBackupPath = '',
    [string]$InstallRoot = 'C:\PDP-One',
    [switch]$SkipDeploymentAgentSetup,
    [switch]$SkipConnectionCheck
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'PDPOne.Common.ps1')
. (Join-Path $PSScriptRoot 'PDPOne.PortableCrypto.ps1')

function Assert-SafeZipEntries([string]$ZipPath, [string]$DestinationRoot) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $root = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\') + '\'
        foreach ($entry in $archive.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $DestinationRoot $entry.FullName))
            if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Portable backup contains an unsafe archive path.' }
        }
    } finally { $archive.Dispose() }
}

function Write-RestoreReport([string]$Status, [string]$ErrorMessage = '') {
    $report = [ordered]@{
        schema_version = 1
        operation = 'bare-metal-portable-restore'
        status = $Status
        install_root = $script:InstallRoot
        database_restored = ($Status -eq 'succeeded')
        private_files_restored = ($Status -eq 'succeeded')
        redis_restored = ($Status -eq 'succeeded')
        tailscale_identity_restored = ($Status -eq 'succeeded')
        environment_restored = ($Status -eq 'succeeded')
        deployment_agent_installed = ($Status -eq 'succeeded' -and -not $script:SkipDeploymentAgentSetup)
        health = $(if ($Status -eq 'succeeded') { 'healthy' } else { 'not-confirmed' })
        secrets_in_report = $false
        completed_at = [DateTime]::UtcNow.ToString('o')
        error = ConvertTo-PDPOneRedactedText $ErrorMessage
    }
    $path = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDP-ONE-PORTABLE-RESTORE-REPORT.json'
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
}

if (-not $PortableBackupPath) {
    $nearby = @(Get-ChildItem -LiteralPath $SourceRoot -Filter 'PDP-One-Portable-Backup-*.pdpone' -File -ErrorAction SilentlyContinue)
    if ($nearby.Count -eq 1) { $PortableBackupPath = $nearby[0].FullName }
    elseif ($nearby.Count -gt 1) { throw 'More than one portable backup is beside RESTORE-PDP-ONE.bat. Keep only the intended file there.' }
    else { $PortableBackupPath = Read-Host 'Enter the full path of the .pdpone backup file' }
}
$PortableBackupPath = (Resolve-Path -LiteralPath $PortableBackupPath).Path
$passphrase = Read-Host 'Enter the portable-backup passphrase' -AsSecureString
$portableBackupSha256 = (Get-FileHash -LiteralPath $PortableBackupPath -Algorithm SHA256).Hash.ToLowerInvariant()
$stage = Join-Path $env:ProgramData "PDP-One\portable-restore\$([Guid]::NewGuid().ToString('N'))"
$plainZip = Join-Path $stage 'portable-backup.zip'
$packageRoot = Join-Path $stage 'package'

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    & icacls.exe $stage /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' *> $null
    Unprotect-PDPOnePortableFile -SourcePath $PortableBackupPath -DestinationPath $plainZip -Passphrase $passphrase
    Assert-SafeZipEntries -ZipPath $plainZip -DestinationRoot $packageRoot
    Expand-Archive -LiteralPath $plainZip -DestinationPath $packageRoot -Force

    $manifestPath = Join-Path $packageRoot 'portable-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Portable manifest is missing.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or -not $manifest.base_restore_verified -or -not $manifest.portable_environment) { throw 'Portable manifest is not eligible for bare-metal restore.' }
    foreach ($entry in $manifest.file_sha256.PSObject.Properties) {
        $member = Join-Path $packageRoot $entry.Name
        if (-not (Test-Path -LiteralPath $member -PathType Leaf)) { throw "Portable backup member $($entry.Name) is missing." }
        $actual = (Get-FileHash -LiteralPath $member -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne [string]$entry.Value) { throw "Portable backup member $($entry.Name) failed integrity validation." }
    }
    foreach ($required in @('database.dump','private_files.tgz','redis_data.tgz','tailscale_state.tgz','environment.env','backup-report.json','source-code.zip')) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $required))) { throw "Required portable member $required is missing." }
    }

    $resumeMarker = Join-Path $InstallRoot '.pdp-one-portable-restore.json'
    $reuseInstallRoot = $false
    if (Test-Path -LiteralPath $InstallRoot) {
        $existing = @(Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction SilentlyContinue)
        if ($existing.Count -gt 0) {
            if (Test-Path -LiteralPath $resumeMarker) {
                $resume = Get-Content -LiteralPath $resumeMarker -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([string]$resume.portable_backup_sha256 -eq $portableBackupSha256) { $reuseInstallRoot = $true }
            }
            if (-not $reuseInstallRoot) { throw "Install root $InstallRoot is not empty and does not match this resumable restore. Nothing was overwritten." }
        }
    } else { New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null }
    if (-not $reuseInstallRoot) {
        Assert-SafeZipEntries -ZipPath (Join-Path $packageRoot 'source-code.zip') -DestinationRoot $InstallRoot
        Expand-Archive -LiteralPath (Join-Path $packageRoot 'source-code.zip') -DestinationPath $InstallRoot -Force
        [ordered]@{ portable_backup_sha256 = $portableBackupSha256; started_at = [DateTime]::UtcNow.ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath $resumeMarker -Encoding UTF8
    }
    Copy-Item -LiteralPath (Join-Path $packageRoot 'environment.env') -Destination (Join-Path $InstallRoot '.env') -Force
    & icacls.exe (Join-Path $InstallRoot '.env') /inheritance:r /grant:r "${env:USERNAME}:F" 'SYSTEM:F' 'Administrators:F' *> $null

    $installer = Join-Path $InstallRoot 'scripts\windows\Install-PDPOne.ps1'
    if (-not (Test-Path -LiteralPath $installer)) { throw 'The source snapshot does not contain the PDP One installer.' }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $installer -SkipPostInstallConnection
    if ($LASTEXITCODE -ne 0) { throw 'PDP One prerequisite/application installation failed.' }
    if (-not (Test-PDPOneDockerEngine)) {
        throw 'Windows/Rancher requires a restart. Restart Windows and run the same RESTORE-PDP-ONE.bat again; the encrypted backup remains unchanged.'
    }

    $testScript = Join-Path $InstallRoot 'scripts\windows\Test-PDPOneBackupRestore.ps1'
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $testScript -BackupPath $packageRoot -PortableEnvironmentPath (Join-Path $packageRoot 'environment.env')
    if ($LASTEXITCODE -ne 0) { throw 'Portable backup failed isolated restore verification on the new installation.' }

    $restoreScript = Join-Path $InstallRoot 'scripts\windows\Restore-PDPOneBackup.ps1'
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $restoreScript -BackupPath $packageRoot -Confirmed -RestoreSettings -RestoreDatabase -RestorePrivateFiles -RestoreRedisData -RestoreTailscaleState -PortableEnvironmentPath (Join-Path $packageRoot 'environment.env')
    if ($LASTEXITCODE -ne 0) { throw 'Portable data restore failed.' }

    if (-not $SkipDeploymentAgentSetup) {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot 'scripts\windows\Install-PDPOneDeploymentAgent.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Deployment Agent installation failed.' }
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot 'scripts\windows\Test-PDPOne.ps1') -SkipChatGPTToolCheck
    if ($LASTEXITCODE -ne 0) { throw 'Restored PDP One health check failed.' }
    if (-not $SkipConnectionCheck) {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot 'scripts\windows\Connect-PDPOneChatGPT.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Restored ChatGPT/Tailscale connection check failed.' }
    }
    Write-RestoreReport -Status 'succeeded'
    Remove-Item -LiteralPath $resumeMarker -Force -ErrorAction SilentlyContinue
    Write-Host 'PDP One portable bare-metal restore completed and passed health checks.' -ForegroundColor Green
} catch {
    Write-RestoreReport -Status 'failed-safely' -ErrorMessage $_.Exception.Message
    throw
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    $passphrase = $null
}
