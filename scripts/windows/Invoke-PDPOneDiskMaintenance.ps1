#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateSet("report", "cleanup", "post-deployment")][string]$Mode = "report",
    [ValidateRange(2, 10)][int]$KeepLocalFinalBackups = 2,
    [string]$ProtectedBackupPath = "",
    [string]$BackupRoot = "C:\ProgramData\PDP-One\backups",
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [string]$ExternalBackupRoot = "D:\BackUp PDP-0NE-14050429-01"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Get-FreeBytes([string]$DriveName) {
    $drive = Get-PSDrive -Name $DriveName -ErrorAction Stop
    return [int64]$drive.Free
}

function Get-DirectoryBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [int64]0 }
    $sum = (Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { return [int64]0 }
    return [int64]$sum
}

function Invoke-PDPOneDockerCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$IgnoreFailure
    )

    $previousPreference = $ErrorActionPreference
    $nativeOutput = @()
    $exitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& docker @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (docker exit code $exitCode)."
    }
    return @($nativeOutput | ForEach-Object { ConvertTo-PDPOneRedactedText ([string]$_) })
}

function Get-VerifiedBackupReport([string]$Path) {
    $reportPath = Join-Path $Path "backup-report.json"
    if (-not (Test-Path -LiteralPath $reportPath)) { return $null }
    try {
        $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not [bool]$report.restore_verified) { return $null }
        return $report
    } catch {
        return $null
    }
}

function Test-ArchivedBackupHashes([string]$Destination, $Report) {
    if ($null -eq $Report.file_sha256) { throw "Backup report does not contain file hashes." }
    foreach ($property in $Report.file_sha256.PSObject.Properties) {
        $target = Join-Path $Destination $property.Name
        if (-not (Test-Path -LiteralPath $target)) { throw "Archived backup file is missing: $($property.Name)" }
        $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$property.Value).ToLowerInvariant()) { throw "Archived backup hash mismatch: $($property.Name)" }
    }
}

function Sync-VerifiedBackup([string]$SourcePath, $Report) {
    if ([string]::IsNullOrWhiteSpace($ExternalBackupRoot)) { return $null }
    $qualifier = Split-Path -Qualifier $ExternalBackupRoot
    if ([string]::IsNullOrWhiteSpace($qualifier) -or -not (Test-Path -LiteralPath $qualifier)) { return $null }

    New-Item -ItemType Directory -Force -Path $ExternalBackupRoot | Out-Null
    $destination = Join-Path $ExternalBackupRoot (Split-Path $SourcePath -Leaf)
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    & robocopy.exe $SourcePath $destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Verified backup could not be copied to the external archive." }
    Test-ArchivedBackupHashes -Destination $destination -Report $Report
    return $destination
}

$maintenanceRoot = "C:\ProgramData\PDP-One\maintenance"
New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportPath = Join-Path $maintenanceRoot ("disk-maintenance-$timestamp.json")

$beforeFree = Get-FreeBytes "C"
$beforeBackupBytes = Get-DirectoryBytes $BackupRoot
$dockerBefore = @()
if (Test-PDPOneDockerEngine) {
    $dockerBefore = @(Invoke-PDPOneDockerCommand -Arguments @("system", "df") -FailureMessage "Docker disk usage could not be read." -IgnoreFailure)
}

$removedBackups = @()
$archivedBackups = @()
$dockerActions = @()
$downloadDirectoriesRemoved = @()

if ($Mode -ne "report") {
    Start-PDPOneRancherDesktop -TimeoutSeconds 300

    $dockerActions += @(Invoke-PDPOneDockerCommand -Arguments @("container", "prune", "--force") -FailureMessage "Stopped Docker containers could not be pruned.")
    $dockerActions += @(Invoke-PDPOneDockerCommand -Arguments @("image", "prune", "--all", "--force") -FailureMessage "Unused Docker images could not be pruned.")
    $dockerActions += @(Invoke-PDPOneDockerCommand -Arguments @("builder", "prune", "--all", "--force") -FailureMessage "Docker build cache could not be pruned.")

    if (Test-Path -LiteralPath $BackupRoot) {
        $protectedResolved = ""
        if ($ProtectedBackupPath -and (Test-Path -LiteralPath $ProtectedBackupPath)) {
            $protectedResolved = (Resolve-Path -LiteralPath $ProtectedBackupPath).Path.TrimEnd('\')
            $protectedReport = Get-VerifiedBackupReport $protectedResolved
            if ($null -ne $protectedReport) {
                $archivedPath = Sync-VerifiedBackup -SourcePath $protectedResolved -Report $protectedReport
                if ($archivedPath) { $archivedBackups += $archivedPath }
            }
        }

        $verified = @()
        Get-ChildItem -LiteralPath $BackupRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^PDP-One-final-Backup-\d{8}-\d{6}$' } |
            Sort-Object Name -Descending |
            ForEach-Object {
                $report = Get-VerifiedBackupReport $_.FullName
                if ($null -ne $report) {
                    $verified += [pscustomobject]@{ Directory = $_; Report = $report }
                }
            }

        $keep = @{}
        foreach ($item in @($verified | Select-Object -First $KeepLocalFinalBackups)) {
            $keep[$item.Directory.FullName.TrimEnd('\').ToLowerInvariant()] = $true
        }
        if ($protectedResolved) { $keep[$protectedResolved.ToLowerInvariant()] = $true }

        foreach ($item in $verified) {
            $candidate = $item.Directory.FullName.TrimEnd('\')
            if ($keep.ContainsKey($candidate.ToLowerInvariant())) { continue }
            $archivedPath = Sync-VerifiedBackup -SourcePath $candidate -Report $item.Report
            if ($archivedPath) { $archivedBackups += $archivedPath }
            Remove-Item -LiteralPath $candidate -Recurse -Force
            $removedBackups += $candidate
        }
    }

    $downloadsRoot = Join-Path $AgentRoot "downloads"
    if (Test-Path -LiteralPath $downloadsRoot) {
        $cutoff = (Get-Date).AddHours(-2)
        Get-ChildItem -LiteralPath $downloadsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt $cutoff } |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
                $downloadDirectoriesRemoved += $_.FullName
            }
    }
}

$afterFree = Get-FreeBytes "C"
$afterBackupBytes = Get-DirectoryBytes $BackupRoot
$dockerAfter = @()
if (Test-PDPOneDockerEngine) {
    $dockerAfter = @(Invoke-PDPOneDockerCommand -Arguments @("system", "df") -FailureMessage "Docker disk usage could not be read after maintenance." -IgnoreFailure)
}

$result = [ordered]@{
    schema_version = 1
    mode = $Mode
    completed_at = (Get-Date).ToUniversalTime().ToString("o")
    keep_local_final_backups = $KeepLocalFinalBackups
    protected_backup_path = $ProtectedBackupPath
    external_backup_root = $ExternalBackupRoot
    c_free_bytes_before = $beforeFree
    c_free_bytes_after = $afterFree
    c_free_bytes_delta = ($afterFree - $beforeFree)
    local_backup_bytes_before = $beforeBackupBytes
    local_backup_bytes_after = $afterBackupBytes
    local_backup_bytes_delta = ($afterBackupBytes - $beforeBackupBytes)
    removed_verified_final_backups = $removedBackups
    externally_archived_backups = $archivedBackups
    removed_agent_download_directories = $downloadDirectoriesRemoved
    docker_before = $dockerBefore
    docker_actions = $dockerActions
    docker_after = $dockerAfter
    volumes_pruned = $false
    database_volume_touched = $false
    private_files_volume_touched = $false
    tailscale_volume_touched = $false
}
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host "PDP One disk maintenance completed without pruning Docker volumes." -ForegroundColor Green
Write-Output $reportPath
