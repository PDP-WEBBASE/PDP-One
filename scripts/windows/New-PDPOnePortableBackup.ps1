#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$OutputDirectory = '',
    [string]$LocalArchiveDirectory = 'D:\BackUp PDP-0NE-14050429-01',
    [switch]$AllowSystemDrive,
    [int]$KdfIterations = 310000
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'PDPOne.Common.ps1')
. (Join-Path $PSScriptRoot 'PDPOne.PortableCrypto.ps1')

function Read-ConfirmedPassphrase {
    $first = Read-Host 'Enter a NEW portable-backup passphrase (minimum 14 characters)' -AsSecureString
    $second = Read-Host 'Enter the same passphrase again' -AsSecureString
    if ($first.Length -lt 14) { throw 'The passphrase must contain at least 14 characters.' }
    $firstText = Get-PDPOnePlainTextFromSecureString $first
    $secondText = Get-PDPOnePlainTextFromSecureString $second
    try {
        if (-not [string]::Equals($firstText, $secondText, [StringComparison]::Ordinal)) { throw 'The passphrases do not match.' }
    } finally { $firstText = $null; $secondText = $null }
    return $first
}

function Assert-PDPOneWritableDirectory([string]$Path, [string]$Purpose) {
    try {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        $probe = Join-Path $resolved ('.pdp-one-write-test-' + [Guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllText($probe, 'write-test', [Text.Encoding]::ASCII)
        Remove-Item -LiteralPath $probe -Force
        return $resolved
    } catch {
        throw "$Purpose is not writable: $Path. $($_.Exception.Message)"
    }
}

function Copy-PDPOneVerifiedArchive([string]$SourcePath, [string]$DestinationDirectory, [string]$FileName, [string]$ExpectedHash) {
    $destination = Join-Path $DestinationDirectory $FileName
    $temporary = "$destination.partial"
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    try {
        Copy-Item -LiteralPath $SourcePath -Destination $temporary -Force
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $ExpectedHash) { throw "Portable archive copy failed SHA-256 verification: $DestinationDirectory" }
        Move-Item -LiteralPath $temporary -Destination $destination -Force
        return $destination
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-PDPOneChildFailure([object[]]$Output, [string]$Fallback) {
    $lines = @($Output | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($lines.Count -eq 0) { return $Fallback }
    $tail = @($lines | Select-Object -Last 25) -join "`n"
    return "$Fallback`n$(ConvertTo-PDPOneRedactedText $tail)"
}

if (-not $OutputDirectory) { $OutputDirectory = Read-Host 'Enter an external-drive or network folder for the encrypted backup' }
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { throw 'An output directory is required.' }
$OutputDirectory = Assert-PDPOneWritableDirectory -Path $OutputDirectory -Purpose 'The external backup directory'
$LocalArchiveDirectory = Assert-PDPOneWritableDirectory -Path $LocalArchiveDirectory -Purpose 'The automatic local archive directory'
$systemRoot = [IO.Path]::GetPathRoot($env:SystemDrive + '\')
$outputRoot = [IO.Path]::GetPathRoot($OutputDirectory)
if (-not $AllowSystemDrive -and [string]::Equals($systemRoot, $outputRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Portable disaster-recovery backup must be stored off the Windows system drive. Use an external drive/network path.'
}
$localRoot = [IO.Path]::GetPathRoot($LocalArchiveDirectory)
if (-not $AllowSystemDrive -and [string]::Equals($systemRoot, $localRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The automatic local portable archive must not be stored on the Windows system drive.'
}

$ProjectRoot = Get-PDPOneProjectRoot
$DistributionRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envPath = Assert-PDPOneConfiguration $ProjectRoot
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stage = Join-Path $env:ProgramData "PDP-One\portable-staging\$timestamp-$([Guid]::NewGuid().ToString('N'))"
$packageRoot = Join-Path $stage 'package'
$sourceStage = Join-Path $stage 'source'
$plainZip = Join-Path $stage 'portable-backup.zip'
$outputName = "PDP-One-Portable-Backup-$timestamp.pdpone"
$encryptedStage = Join-Path $stage $outputName
$passphrase = Read-ConfirmedPassphrase
$currentStep = 'initialization'
$createdArchives = @()

try {
    $currentStep = 'secure-staging'
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    & icacls.exe $stage /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' *> $null

    $currentStep = 'base-backup'
    # Invoke the signed local script in-process. Windows PowerShell 5.1 can
    # otherwise promote harmless native stderr (for example Docker's
    # "Unable to find image ... locally") into a terminating RemoteException.
    $baseBackupScript = Join-Path $PSScriptRoot 'New-PDPOneBackup.ps1'
    $backupOutput = @(& $baseBackupScript -Kind manual -DeploymentId "portable-$timestamp")
    $backupPath = @($backupOutput | ForEach-Object { [string]$_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Container -ErrorAction SilentlyContinue } | Select-Object -Last 1)
    if ($backupPath.Count -ne 1) { throw (Get-PDPOneChildFailure -Output $backupOutput -Fallback 'Base backup completed without returning a valid backup directory.') }
    $backupPath = [string]$backupPath[0]

    $currentStep = 'isolated-restore-verification'
    $verifyScript = Join-Path $PSScriptRoot 'Test-PDPOneBackupRestore.ps1'
    $verifyOutput = @(& $verifyScript -BackupPath $backupPath)

    $currentStep = 'portable-package'
    Get-ChildItem -LiteralPath $backupPath -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $packageRoot $_.Name) -Force }
    Copy-Item -LiteralPath $envPath -Destination (Join-Path $packageRoot 'environment.env') -Force

    New-Item -ItemType Directory -Path $sourceStage -Force | Out-Null
    & robocopy.exe $DistributionRoot $sourceStage /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env 'PDP-ONE-LOCAL-LOGIN.txt' /XD .git work node_modules .next outputs
    if ($LASTEXITCODE -gt 7) { throw 'Portable source-code snapshot failed.' }
    Compress-Archive -Path (Join-Path $sourceStage '*') -DestinationPath (Join-Path $packageRoot 'source-code.zip') -CompressionLevel Optimal -Force

    $lastDeployment = Join-Path $env:ProgramData 'PDP-One\deployment-agent\state\last-deployment.json'
    $sourceCommit = 'installed-current'
    if (Test-Path -LiteralPath $lastDeployment) {
        try { $sourceCommit = [string]((Get-Content -LiteralPath $lastDeployment -Raw -Encoding UTF8 | ConvertFrom-Json).approved_commit) } catch { }
    }
    $distributionVersion = 'unversioned'
    $versionPath = Join-Path $DistributionRoot 'release\VERSION'
    if (Test-Path -LiteralPath $versionPath) { $distributionVersion = ([IO.File]::ReadAllText($versionPath)).Trim() }
    $hashes = [ordered]@{}
    Get-ChildItem -LiteralPath $packageRoot -File | Sort-Object Name | ForEach-Object {
        $hashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest = [ordered]@{
        schema_version = 1
        format = 'PDP-One-Portable-Backup'
        created_at = [DateTime]::UtcNow.ToString('o')
        source_commit = $sourceCommit
        source_distribution_version = $distributionVersion
        base_backup_id = Split-Path $backupPath -Leaf
        base_restore_verified = $true
        portable_environment = $true
        source_snapshot = $true
        encryption = 'AES-256-CBC'
        authentication = 'HMAC-SHA256'
        kdf = 'PBKDF2-HMAC-SHA256'
        kdf_iterations = $KdfIterations
        file_sha256 = $hashes
        secrets_in_manifest = $false
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $packageRoot 'portable-manifest.json') -Encoding UTF8
    Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $plainZip -CompressionLevel Optimal -Force

    $currentStep = 'encryption'
    Protect-PDPOnePortableFile -SourcePath $plainZip -DestinationPath $encryptedStage -Passphrase $passphrase -Iterations $KdfIterations
    $portableHash = (Get-FileHash -LiteralPath $encryptedStage -Algorithm SHA256).Hash.ToLowerInvariant()

    $currentStep = 'external-copy'
    $externalPath = Copy-PDPOneVerifiedArchive -SourcePath $encryptedStage -DestinationDirectory $OutputDirectory -FileName $outputName -ExpectedHash $portableHash
    $createdArchives += $externalPath
    if ([string]::Equals($OutputDirectory.TrimEnd('\'), $LocalArchiveDirectory.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        $localPath = $externalPath
    } else {
        $currentStep = 'automatic-local-copy'
        $localPath = Copy-PDPOneVerifiedArchive -SourcePath $encryptedStage -DestinationDirectory $LocalArchiveDirectory -FileName $outputName -ExpectedHash $portableHash
        $createdArchives += $localPath
    }

    $currentStep = 'success-report'
    $safeReport = [ordered]@{
        schema_version = 1
        status = 'succeeded'
        operation = 'create-portable-encrypted-backup'
        file_name = $outputName
        size_bytes = (Get-Item -LiteralPath $externalPath).Length
        sha256 = $portableHash
        base_backup_id = Split-Path $backupPath -Leaf
        isolated_restore_verified = $true
        stored_off_system_drive = (-not [string]::Equals($systemRoot, $outputRoot, [StringComparison]::OrdinalIgnoreCase))
        external_copy = $externalPath
        automatic_local_copy = $localPath
        copies_sha256_verified = $true
        dpapi_independent = $true
        passphrase_stored = $false
        completed_at = [DateTime]::UtcNow.ToString('o')
    }
    $reportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDP-ONE-PORTABLE-BACKUP-REPORT.json'
    $safeReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Host "Portable encrypted backup created: $externalPath" -ForegroundColor Green
    Write-Host "Automatic local copy created: $localPath" -ForegroundColor Green
    Write-Host 'Store the passphrase separately. It cannot be recovered from GitHub or the backup file.' -ForegroundColor Yellow
    Write-Output $externalPath
} catch {
    $failure = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $failureReport = [ordered]@{
        schema_version = 1
        status = 'failed-safely'
        operation = 'create-portable-encrypted-backup'
        failed_step = $currentStep
        error = $failure
        created_archives = @($createdArchives)
        existing_data_deleted = $false
        existing_backups_deleted = $false
        completed_at = [DateTime]::UtcNow.ToString('o')
    }
    $failureReportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDP-ONE-PORTABLE-BACKUP-REPORT.json'
    $failureReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $failureReportPath -Encoding UTF8
    Write-Host "Portable backup stopped safely at step: $currentStep" -ForegroundColor Red
    Write-Host $failure -ForegroundColor Red
    Write-Host "Safe report: $failureReportPath" -ForegroundColor Yellow
    throw
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    $passphrase = $null
}
