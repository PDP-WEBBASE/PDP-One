#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateSet("initial", "final", "manual")][string]$Kind = "manual",
    [string]$DeploymentId = "",
    [string]$ApprovedCommit = "",
    [string]$BackupRoot = "C:\ProgramData\PDP-One\backups"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Get-ComposeVolume([string]$LogicalName) {
    $name = (& docker volume ls --filter "label=com.docker.compose.project=pdp-one" --filter "label=com.docker.compose.volume=$LogicalName" --format "{{.Name}}" | Select-Object -First 1)
    if (-not $name) { throw "Required Docker volume $LogicalName was not found." }
    return ([string]$name).Trim()
}

function Sync-PDPOneExternalBackup([string]$SourcePath, [string]$DestinationPath) {
    New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null
    & robocopy.exe $SourcePath $DestinationPath /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP
    if ($LASTEXITCODE -gt 7) { throw "External backup mirror failed." }
}

$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
Start-PDPOneRancherDesktop -TimeoutSeconds 300
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$stableMarker = $null
$stableMarkerPath = Join-Path $ProjectRoot "release\stable-mode.json"
if (Test-Path -LiteralPath $stableMarkerPath) {
    $stableMarker = Get-Content -LiteralPath $stableMarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
$stableReleaseRequested = [bool](
    $Kind -eq "final" -and
    $ApprovedCommit -match '^[0-9a-f]{40}$' -and
    $null -ne $stableMarker -and
    [bool]$stableMarker.activate_standard_after_verified_backup
)
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupId = "PDP-One-$Kind-Backup-$timestamp"
$backupPath = Join-Path $BackupRoot $backupId
New-Item -ItemType Directory -Force -Path $backupPath | Out-Null
& icacls.exe $backupPath /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" *> $null

$externalRoot = Get-PDPOneEnvValue -Path $envPath -Name "PDP_EXTERNAL_BACKUP_ROOT"
if ([string]::IsNullOrWhiteSpace($externalRoot) -and $stableReleaseRequested) {
    $externalRoot = [string]$stableMarker.external_backup_root
}
$externalBackupPath = $null
if (-not [string]::IsNullOrWhiteSpace($externalRoot)) {
    $externalRoot = [Environment]::ExpandEnvironmentVariables($externalRoot.Trim())
    $driveRoot = [IO.Path]::GetPathRoot($externalRoot)
    if (-not $driveRoot -or -not (Test-Path -LiteralPath $driveRoot)) {
        throw "The configured external backup drive is not available."
    }
    New-Item -ItemType Directory -Force -Path $externalRoot | Out-Null
    $externalBackupPath = Join-Path $externalRoot $backupId
}
if ($stableReleaseRequested -and [bool]$stableMarker.require_external_backup -and -not $externalBackupPath) {
    throw "Stable release backup requires the approved external mirror."
}

$volumes = [ordered]@{
    postgres_data = (Get-ComposeVolume "postgres_data")
    private_files = (Get-ComposeVolume "private_files")
    redis_data = (Get-ComposeVolume "redis_data")
    tailscale_state = (Get-ComposeVolume "tailscale_state")
}
$dbContainer = (& docker compose ps -q db).Trim()
if (-not $dbContainer) { throw "PostgreSQL container is not running." }
$dbImage = (& docker inspect --format '{{.Config.Image}}' $dbContainer).Trim()
$utilityContainer = (& docker compose ps -q nginx).Trim()
$utilityImage = (& docker inspect --format '{{.Config.Image}}' $utilityContainer).Trim()
$dbName = Get-PDPOneEnvValue $envPath "POSTGRES_DB"
$dbUser = Get-PDPOneEnvValue $envPath "POSTGRES_USER"
$dumpName = "database.dump"
$containerDump = "/tmp/$backupId.dump"

& docker compose exec -T db pg_dump --username $dbUser --dbname $dbName --format custom --file $containerDump
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL dump failed." }
try {
    & docker cp "${dbContainer}:$containerDump" (Join-Path $backupPath $dumpName)
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL dump could not be copied from the container." }
} finally { & docker compose exec -T db rm -f $containerDump *> $null }

& docker run --rm --volume "$($volumes.private_files):/source:ro" --volume "${backupPath}:/backup" --entrypoint sh $utilityImage -c "cd /source && tar -czf /backup/private_files.tgz ."
if ($LASTEXITCODE -ne 0) { throw "Private-files archive failed." }
& docker run --rm --volume "$($volumes.redis_data):/source:ro" --volume "${backupPath}:/backup" --entrypoint sh $utilityImage -c "cd /source && tar -czf /backup/redis_data.tgz ."
if ($LASTEXITCODE -ne 0) { throw "Redis-data archive failed." }
& docker run --rm --volume "$($volumes.tailscale_state):/source:ro" --volume "${backupPath}:/backup" --entrypoint sh $utilityImage -c "cd /source && tar -czf /backup/tailscale_state.tgz ."
if ($LASTEXITCODE -ne 0) { throw "Tailscale-state archive failed." }

Protect-PDPOneSecretFile -InputPath $envPath -OutputPath (Join-Path $backupPath "environment.dpapi")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "docker-compose.yml") -Destination (Join-Path $backupPath "docker-compose.yml")
$scriptHashes = @{}
Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "scripts\windows") -Filter "*.ps1" | ForEach-Object {
    $scriptHashes[$_.Name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
}
$volumeArguments = @($volumes.Values)
$volumeState = @(& docker volume inspect $volumeArguments | ConvertFrom-Json | ForEach-Object {
    [ordered]@{ name = $_.Name; driver = $_.Driver; mountpoint_recorded = [bool]$_.Mountpoint }
})
$serviceState = @(& docker compose --profile tunnel ps --format json 2>$null | ForEach-Object {
    try {
        $item = $_ | ConvertFrom-Json
        $health = ""
        if ($null -ne $item.PSObject.Properties["Health"]) { $health = [string]$item.Health }
        [ordered]@{ service = $item.Service; state = $item.State; health = $health }
    } catch { }
})
$files = @("database.dump", "private_files.tgz", "redis_data.tgz", "tailscale_state.tgz", "environment.dpapi", "docker-compose.yml")
$hashes = @{}
foreach ($file in $files) { $hashes[$file] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupPath $file)).Hash.ToLowerInvariant() }

$manifest = [ordered]@{
    schema_version = 2
    backup_id = $backupId
    kind = $Kind
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    project_root = $ProjectRoot
    source_commit = $(if ($ApprovedCommit) { $ApprovedCommit } else { "installed-current" })
    deployment_id = $DeploymentId
    approved_commit = $ApprovedCommit
    docker = (& docker version --format '{{.Server.Version}}')
    compose = (& docker compose version --short)
    database_image = $dbImage
    utility_image = $utilityImage
    database_name = $dbName
    database_user = $dbUser
    volumes = $volumes
    volume_state = $volumeState
    service_state = $serviceState
    script_sha256 = $scriptHashes
    file_sha256 = $hashes
    restore_verified = $false
    production_changed = $false
    token_rotated = $false
    secrets_in_report = $false
    external_backup_required = [bool]$externalBackupPath
    external_backup_path = $externalBackupPath
    external_backup_copied = $false
    stable_release_requested = $stableReleaseRequested
    stable_release_version = $(if ($stableReleaseRequested) { [string]$stableMarker.release_version } else { $null })
    activate_standard_after_restore = $stableReleaseRequested
    target_change_management_mode = $(if ($stableReleaseRequested) { "standard" } else { $null })
    target_trial_mode = $(if ($stableReleaseRequested) { $false } else { $null })
}
$reportPath = Join-Path $backupPath "backup-report.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

if ($externalBackupPath) {
    Sync-PDPOneExternalBackup -SourcePath $backupPath -DestinationPath $externalBackupPath
    $manifest.external_backup_copied = $true
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Copy-Item -LiteralPath $reportPath -Destination (Join-Path $externalBackupPath "backup-report.json") -Force
}

Write-Host "Backup created: $backupId" -ForegroundColor Green
Write-Output $backupPath
