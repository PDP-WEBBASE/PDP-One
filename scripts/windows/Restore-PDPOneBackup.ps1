#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [switch]$Confirmed,
    [switch]$AutomaticRollback,
    [switch]$RestoreSettings,
    [switch]$RestoreDatabase,
    [switch]$RestorePrivateFiles,
    [switch]$RestoreRedisData,
    [switch]$RestoreTailscaleState,
    [string]$PortableEnvironmentPath = ''
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
if (-not $Confirmed -and -not $AutomaticRollback) { throw "Restore requires explicit confirmation or an authorized automatic rollback." }
$reportPath = Join-Path $BackupPath "backup-report.json"
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $report.restore_verified) { throw "Restore is blocked because this backup has not passed isolated verification." }
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$dbName = [string]$report.database_name
$dbUser = [string]$report.database_user

& docker compose --profile tunnel stop backend worker beat mcp web nginx tailscale *> $null
if ($RestoreSettings) {
    Copy-Item -LiteralPath $envPath -Destination "$envPath.before-restore" -Force
    if ($PortableEnvironmentPath) {
        Copy-Item -LiteralPath $PortableEnvironmentPath -Destination $envPath -Force
    } else {
        Unprotect-PDPOneSecretFile -InputPath (Join-Path $BackupPath "environment.dpapi") -OutputPath $envPath
    }
}
if ($RestoreDatabase) {
    $dbContainer = (& docker compose ps -q db).Trim()
    & docker cp (Join-Path $BackupPath "database.dump") "${dbContainer}:/tmp/pdp-one-restore.dump"
    & docker compose exec -T db dropdb --username $dbUser --if-exists --force $dbName
    & docker compose exec -T db createdb --username $dbUser --owner $dbUser $dbName
    & docker compose exec -T db pg_restore --username $dbUser --dbname $dbName --no-owner --no-privileges --exit-on-error /tmp/pdp-one-restore.dump
    if ($LASTEXITCODE -ne 0) { throw "Database restore failed." }
    & docker compose exec -T db rm -f /tmp/pdp-one-restore.dump *> $null
}
if ($RestorePrivateFiles) {
    & docker run --rm --volume "$($report.volumes.private_files):/target" --volume "${BackupPath}:/backup:ro" --entrypoint sh $report.utility_image -c "find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf /backup/private_files.tgz -C /target"
    if ($LASTEXITCODE -ne 0) { throw "Private-files restore failed." }
}
if ($RestoreRedisData) {
    & docker compose stop redis *> $null
    & docker run --rm --volume "$($report.volumes.redis_data):/target" --volume "${BackupPath}:/backup:ro" --entrypoint sh $report.utility_image -c "find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf /backup/redis_data.tgz -C /target"
    if ($LASTEXITCODE -ne 0) { throw "Redis-data restore failed." }
}
if ($RestoreTailscaleState) {
    & docker run --rm --volume "$($report.volumes.tailscale_state):/target" --volume "${BackupPath}:/backup:ro" --entrypoint sh $report.utility_image -c "find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf /backup/tailscale_state.tgz -C /target"
    if ($LASTEXITCODE -ne 0) { throw "Tailscale-state restore failed." }
}
& docker compose --profile tunnel up --detach --no-build
if ($LASTEXITCODE -ne 0 -or -not (Wait-PDPOneUrl "http://127.0.0.1:8080/healthz" 180)) { throw "Restored services did not become healthy." }
$null = Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot -AcceptCurrent
Write-Host "Selected PDP One backup components were restored successfully." -ForegroundColor Green
