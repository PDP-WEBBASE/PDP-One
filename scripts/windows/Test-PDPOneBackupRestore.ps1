#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [string]$PortableEnvironmentPath = ''
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Sync-PDPOneVerifiedExternalBackup($Report, [string]$SourcePath, [string]$ReportPath) {
    $externalRequired = $false
    if ($null -ne $Report.PSObject.Properties["external_backup_required"]) {
        $externalRequired = [bool]$Report.external_backup_required
    }
    if (-not $externalRequired) { return }
    $externalPath = [string]$Report.external_backup_path
    if ([string]::IsNullOrWhiteSpace($externalPath)) { throw "External backup path is missing from the report." }
    $driveRoot = [IO.Path]::GetPathRoot($externalPath)
    if (-not $driveRoot -or -not (Test-Path -LiteralPath $driveRoot)) { throw "External backup drive is not available during restore verification." }
    New-Item -ItemType Directory -Force -Path $externalPath | Out-Null
    & robocopy.exe $SourcePath $externalPath /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP
    if ($LASTEXITCODE -gt 7) { throw "Verified backup could not be synchronized to the external drive." }
    foreach ($entry in $Report.file_sha256.PSObject.Properties) {
        $externalMember = Join-Path $externalPath $entry.Name
        if (-not (Test-Path -LiteralPath $externalMember)) { throw "External backup member $($entry.Name) is missing." }
        $externalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $externalMember).Hash.ToLowerInvariant()
        if ($externalHash -ne [string]$entry.Value) { throw "External backup member $($entry.Name) failed integrity validation." }
    }
    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $externalPath "backup-report.json") -Force
}

$reportPath = Join-Path $BackupPath "backup-report.json"
if (-not (Test-Path -LiteralPath $reportPath)) { throw "Backup report is missing." }
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $report.file_sha256.PSObject.Properties) {
    $path = Join-Path $BackupPath $entry.Name
    if (-not (Test-Path -LiteralPath $path)) { throw "Backup member $($entry.Name) is missing." }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne [string]$entry.Value) { throw "Backup member $($entry.Name) failed integrity validation." }
}

$temporaryEnv = Join-Path $env:TEMP ("pdp-one-env-check-" + [Guid]::NewGuid().ToString("N"))
try {
    if ($PortableEnvironmentPath) {
        Copy-Item -LiteralPath $PortableEnvironmentPath -Destination $temporaryEnv -Force
    } else {
        Unprotect-PDPOneSecretFile -InputPath (Join-Path $BackupPath "environment.dpapi") -OutputPath $temporaryEnv
    }
    if ((Get-Item -LiteralPath $temporaryEnv).Length -lt 64) { throw "The protected environment backup is invalid." }
} finally { Remove-Item -LiteralPath $temporaryEnv -Force -ErrorAction SilentlyContinue }

$containerName = "pdp-one-restore-test-" + [Guid]::NewGuid().ToString("N").Substring(0, 10)
$password = New-PDPOneSecret 24
$dbName = [string]$report.database_name
$dbUser = [string]$report.database_user
try {
    & docker run --detach --name $containerName --env "POSTGRES_PASSWORD=$password" --env "POSTGRES_DB=$dbName" --env "POSTGRES_USER=$dbUser" $report.database_image *> $null
    if ($LASTEXITCODE -ne 0) { throw "Isolated PostgreSQL restore container failed to start." }
    $ready = $false
    foreach ($attempt in 1..60) {
        & docker exec $containerName pg_isready -U $dbUser -d $dbName *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "Isolated PostgreSQL restore container did not become ready." }
    & docker cp (Join-Path $BackupPath "database.dump") "${containerName}:/tmp/database.dump"
    & docker exec $containerName pg_restore --username $dbUser --dbname $dbName --no-owner --no-privileges --exit-on-error /tmp/database.dump
    if ($LASTEXITCODE -ne 0) { throw "Isolated PostgreSQL restore failed." }
    $migrationCount = (& docker exec $containerName psql -U $dbUser -d $dbName -Atc "select count(*) from django_migrations;").Trim()
    $contractCount = (& docker exec $containerName psql -U $dbUser -d $dbName -Atc "select count(*) from core_contract;").Trim()
    if ($migrationCount -notmatch '^\d+$' -or $contractCount -notmatch '^\d+$') { throw "Restored database validation queries failed." }

    & docker run --rm --volume "${BackupPath}:/backup:ro" --entrypoint sh $report.utility_image -c "tar -tzf /backup/private_files.tgz >/dev/null && tar -tzf /backup/redis_data.tgz >/dev/null && tar -tzf /backup/tailscale_state.tgz >/dev/null"
    if ($LASTEXITCODE -ne 0) { throw "File archive validation failed." }
    $report.restore_verified = $true
    $report | Add-Member -NotePropertyName restore_verified_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
    $report | Add-Member -NotePropertyName restore_test -NotePropertyValue ([ordered]@{ isolated_database = $true; migrations = [int]$migrationCount; contracts = [int]$contractCount; archives = $true; protected_environment = $true; portable_environment = [bool]$PortableEnvironmentPath; external_mirror = [bool]$report.external_backup_required }) -Force
    if ($null -ne $report.PSObject.Properties["external_backup_copied"] -and [bool]$report.external_backup_required) {
        $report.external_backup_copied = $true
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Sync-PDPOneVerifiedExternalBackup -Report $report -SourcePath $BackupPath -ReportPath $reportPath

    $activateStandard = $false
    if ($null -ne $report.PSObject.Properties["activate_standard_after_restore"]) {
        $activateStandard = [bool]$report.activate_standard_after_restore
    }
    if ($activateStandard) {
        $activationScript = Join-Path $PSScriptRoot "Activate-PDPOneStandardMode.ps1"
        if (-not (Test-Path -LiteralPath $activationScript)) { throw "Stable-mode activation script is missing." }
        $activationOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $activationScript -BackupPath $BackupPath -ApprovedCommit ([string]$report.approved_commit) -DeploymentId ([string]$report.deployment_id))
        if ($LASTEXITCODE -ne 0) { throw "Stable-mode activation failed after restore verification." }
        $report | Add-Member -NotePropertyName standard_mode_activated -NotePropertyValue $true -Force
        $report | Add-Member -NotePropertyName standard_mode_activated_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
        if ($activationOutput.Count -gt 0) {
            $report | Add-Member -NotePropertyName stable_release_state_path -NotePropertyValue ([string]$activationOutput[-1]) -Force
        }
        $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Sync-PDPOneVerifiedExternalBackup -Report $report -SourcePath $BackupPath -ReportPath $reportPath
    }
    Write-Host "Backup restore verification succeeded in an isolated database." -ForegroundColor Green
} finally {
    & docker rm --force $containerName *> $null
}
