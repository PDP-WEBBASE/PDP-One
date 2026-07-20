#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$OutputDirectory = '',
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

if (-not $OutputDirectory) { $OutputDirectory = Read-Host 'Enter an external-drive or network folder for the encrypted backup' }
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { throw 'An output directory is required.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$systemRoot = [IO.Path]::GetPathRoot($env:SystemDrive + '\')
$outputRoot = [IO.Path]::GetPathRoot($OutputDirectory)
if (-not $AllowSystemDrive -and [string]::Equals($systemRoot, $outputRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Portable disaster-recovery backup must be stored off the Windows system drive. Use an external drive/network path.'
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
$outputPath = Join-Path $OutputDirectory $outputName
$passphrase = Read-ConfirmedPassphrase

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    & icacls.exe $stage /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' *> $null

    $backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'New-PDPOneBackup.ps1') -Kind manual -DeploymentId "portable-$timestamp")
    if ($LASTEXITCODE -ne 0) { throw 'Base backup creation failed.' }
    $backupPath = [string]$backupOutput[-1]
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Test-PDPOneBackupRestore.ps1') -BackupPath $backupPath
    if ($LASTEXITCODE -ne 0) { throw 'Base backup isolated restore verification failed.' }

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
    Protect-PDPOnePortableFile -SourcePath $plainZip -DestinationPath $outputPath -Passphrase $passphrase -Iterations $KdfIterations

    $safeReport = [ordered]@{
        schema_version = 1
        status = 'succeeded'
        operation = 'create-portable-encrypted-backup'
        file_name = $outputName
        size_bytes = (Get-Item -LiteralPath $outputPath).Length
        sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        base_backup_id = Split-Path $backupPath -Leaf
        isolated_restore_verified = $true
        stored_off_system_drive = (-not [string]::Equals($systemRoot, $outputRoot, [StringComparison]::OrdinalIgnoreCase))
        dpapi_independent = $true
        passphrase_stored = $false
        completed_at = [DateTime]::UtcNow.ToString('o')
    }
    $reportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDP-ONE-PORTABLE-BACKUP-REPORT.json'
    $safeReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Host "Portable encrypted backup created: $outputPath" -ForegroundColor Green
    Write-Host 'Store the passphrase separately. It cannot be recovered from GitHub or the backup file.' -ForegroundColor Yellow
    Write-Output $outputPath
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    $passphrase = $null
}
