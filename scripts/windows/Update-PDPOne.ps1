#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$SourceRoot = "",
    [string]$InstalledRoot = "",
    [string]$ApprovedCommit = "",
    [string]$DeploymentId = "",
    [string]$BackupPath = "",
    [string]$CodeArchive = "",
    [switch]$AgentAuthorized
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $SourceRoot) { $SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
if (-not $InstalledRoot) { $InstalledRoot = Get-PDPOneProjectRoot }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$InstalledRoot = (Resolve-Path -LiteralPath $InstalledRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "docker-compose.yml"))) { throw "Update source is invalid." }
Start-PDPOneRancherDesktop -TimeoutSeconds 300
$envPath = Assert-PDPOneConfiguration -ProjectRoot $InstalledRoot
$tokenBefore = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue $envPath "PDP_MCP_PATH_TOKEN")

if ($AgentAuthorized) {
    if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or -not $DeploymentId -or -not $BackupPath -or -not $CodeArchive) {
        throw "Agent-authorized update is missing its locked commit, deployment, backup, or rollback snapshot."
    }
} else {
    Write-Host "Emergency manual update: creating and restore-verifying a backup first." -ForegroundColor Yellow
    $backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneBackup.ps1") -Kind manual -DeploymentId "manual-$((Get-Date).ToString('yyyyMMdd-HHmmss'))")
    $BackupPath = [string]$backupOutput[-1]
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOneBackupRestore.ps1") -BackupPath $BackupPath
    if ($LASTEXITCODE -ne 0) { throw "Emergency update stopped because backup verification failed." }
    $stage = Join-Path $env:TEMP ("pdp-one-code-before-update-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    & robocopy.exe $InstalledRoot $stage /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Rollback code snapshot failed." }
    $CodeArchive = Join-Path $BackupPath "code-before-deployment.zip"
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $CodeArchive -Force
    Remove-Item -LiteralPath $stage -Recurse -Force
}

$backupReport = Get-Content -LiteralPath (Join-Path $BackupPath "backup-report.json") -Raw | ConvertFrom-Json
if (-not $backupReport.restore_verified) { throw "Update is blocked: the linked backup has not passed restore verification." }

$migrationAttempted = $false
$productionTouched = $false
try {
    Set-Location $InstalledRoot
    & docker compose --profile tunnel stop backend worker beat mcp web nginx tailscale
    if ($LASTEXITCODE -ne 0) { throw "Application services could not be stopped cleanly." }
    $productionTouched = $true

    & robocopy.exe $SourceRoot $InstalledRoot /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Approved application files could not be copied." }
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Updated Docker Compose configuration is invalid." }

    & docker compose build backend worker beat mcp web
    if ($LASTEXITCODE -ne 0) { throw "Updated images could not be built." }
    & docker compose up --detach db redis
    if ($LASTEXITCODE -ne 0) { throw "Database dependencies could not be started." }
    $migrationAttempted = $true
    & docker compose run --rm backend python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Controlled database migration failed." }

    & docker compose --profile tunnel up --detach --no-build
    if ($LASTEXITCODE -ne 0) { throw "Updated services failed to start." }
    if (-not (Wait-PDPOneUrl "http://127.0.0.1:8080/healthz" 180)) { throw "Updated local health timed out." }
    $tokenAfter = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue $envPath "PDP_MCP_PATH_TOKEN")
    if ($tokenBefore -ne $tokenAfter) { throw "Update changed the MCP path token without authorization." }

    $connectivity = & (Join-Path $InstalledRoot "scripts\windows\Repair-PDPOneConnectivity.ps1") -ProjectRoot $InstalledRoot -RepairAttempts 3
    if ($null -eq $connectivity -or [string]$connectivity.status -ne "succeeded") {
        throw "Updated services are locally healthy, but the stable public route could not be verified."
    }

    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstalledRoot "scripts\windows\Test-PDPOne.ps1") -SkipChatGPTToolCheck
    if ($LASTEXITCODE -ne 0) { throw "Layered post-update health failed." }

    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstalledRoot "scripts\windows\Register-PDPOneStartupTask.ps1") -ProjectRoot $InstalledRoot
    if ($LASTEXITCODE -ne 0) { throw "Stable Windows startup tasks could not be registered." }

    Write-Host "PDP One updated to the locked release and passed health checks. Tokens, data and volumes were preserved." -ForegroundColor Green
} catch {
    $failure = $_.Exception.Message
    if ($productionTouched) {
        Write-Host "Update failed. Starting automatic rollback ..." -ForegroundColor Red
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Rollback-PDPOne.ps1") -BackupPath $BackupPath -CodeArchive $CodeArchive -Automatic -RestoreDatabase:$migrationAttempted
        $rollbackCode = $LASTEXITCODE
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneDiagnostics.ps1") -FailureMessage $failure -DeploymentId $DeploymentId -BackupId $backupReport.backup_id -RollbackResult $(if ($rollbackCode -eq 0) { "healthy" } else { "failed" }) -Stage "update"
        if ($rollbackCode -ne 0) { throw "Update failed and automatic rollback also failed: $failure" }
        throw "Update failed; automatic rollback returned the previous version to health: $failure"
    }
    throw
}
