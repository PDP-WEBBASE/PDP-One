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

function Invoke-PDPOneDockerCompose {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$IgnoreFailure,
        [switch]$Quiet
    )

    $previousPreference = $ErrorActionPreference
    $nativeOutput = @()
    $exitCode = -1
    try {
        # Docker Compose writes normal progress messages such as "Restarting"
        # to stderr. In Windows PowerShell 5.1, an agent-captured stderr stream
        # can become NativeCommandError while the native exit code is still 0.
        # Temporarily keep native stderr non-terminating and trust exit code.
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& docker compose @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if (-not $Quiet -and $nativeOutput.Count -gt 0) {
        $nativeText = ConvertTo-PDPOneRedactedText (($nativeOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if (-not [string]::IsNullOrWhiteSpace($nativeText)) { Write-Host $nativeText }
    }

    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (docker compose exit code $exitCode)."
    }
    return $exitCode
}

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
    Invoke-PDPOneDockerCompose -Arguments @("--profile", "tunnel", "stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale") -FailureMessage "Application services could not be stopped cleanly." | Out-Null
    $productionTouched = $true

    & robocopy.exe $SourceRoot $InstalledRoot /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Approved application files could not be copied." }
    Invoke-PDPOneDockerCompose -Arguments @("config", "--quiet") -FailureMessage "Updated Docker Compose configuration is invalid." | Out-Null

    Invoke-PDPOneDockerCompose -Arguments @("build", "backend", "worker", "beat", "mcp", "web") -FailureMessage "Updated images could not be built." | Out-Null
    Invoke-PDPOneDockerCompose -Arguments @("up", "--detach", "db", "redis") -FailureMessage "Database dependencies could not be started." | Out-Null
    $migrationAttempted = $true
    Invoke-PDPOneDockerCompose -Arguments @("run", "--rm", "backend", "python", "manage.py", "migrate", "--noinput") -FailureMessage "Controlled database migration failed." | Out-Null

    Invoke-PDPOneDockerCompose -Arguments @("--profile", "tunnel", "up", "--detach", "--no-build") -FailureMessage "Updated services failed to start." | Out-Null
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

    # Space maintenance is intentionally non-transactional and runs only after
    # the release is healthy. It never prunes Docker volumes. A maintenance
    # failure is recorded as a warning and must not roll back a healthy release.
    try {
        $maintenanceOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstalledRoot "scripts\windows\Invoke-PDPOneDiskMaintenance.ps1") -Mode post-deployment -KeepLocalFinalBackups 2 -ProtectedBackupPath $BackupPath)
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "PDP One was updated successfully, but automatic disk maintenance returned a failure."
        } elseif ($maintenanceOutput.Count -gt 0) {
            Write-Host "Disk maintenance report: $([string]$maintenanceOutput[-1])" -ForegroundColor DarkGreen
        }
    } catch {
        Write-Warning "PDP One was updated successfully, but automatic disk maintenance failed: $(ConvertTo-PDPOneRedactedText $_.Exception.Message)"
    }

    Write-Host "PDP One updated to the locked release and passed health checks. Tokens, data and volumes were preserved." -ForegroundColor Green
} catch {
    $failure = $_.Exception.Message
    if ($productionTouched) {
        Write-Host "Update failed. Starting automatic rollback ..." -ForegroundColor Red

        # Do not pass a Boolean value through -RestoreDatabase:$value to a new
        # powershell.exe process. Windows PowerShell 5.1 serializes that token as
        # text and switch binding fails. Add the switch only when it is needed.
        $rollbackArgs = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $PSScriptRoot "Rollback-PDPOne.ps1"),
            "-BackupPath", $BackupPath,
            "-CodeArchive", $CodeArchive,
            "-Automatic"
        )
        if ($migrationAttempted) { $rollbackArgs += "-RestoreDatabase" }
        & powershell.exe @rollbackArgs
        $rollbackCode = $LASTEXITCODE

        # Empty PowerShell arguments disappear at the native-process boundary.
        # Always provide safe non-empty diagnostic identifiers for manual runs.
        $diagnosticDeploymentId = $(if ([string]::IsNullOrWhiteSpace($DeploymentId)) { "manual-update" } else { $DeploymentId })
        $diagnosticBackupId = $(if ($null -ne $backupReport -and -not [string]::IsNullOrWhiteSpace([string]$backupReport.backup_id)) { [string]$backupReport.backup_id } else { "unknown-backup" })
        $diagnosticRollback = $(if ($rollbackCode -eq 0) { "healthy" } else { "failed" })
        $diagnosticArgs = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $PSScriptRoot "New-PDPOneDiagnostics.ps1"),
            "-FailureMessage", $failure,
            "-DeploymentId", $diagnosticDeploymentId,
            "-BackupId", $diagnosticBackupId,
            "-RollbackResult", $diagnosticRollback,
            "-Stage", "update"
        )
        & powershell.exe @diagnosticArgs

        if ($rollbackCode -ne 0) { throw "Update failed and automatic rollback also failed: $failure" }
        throw "Update failed; automatic rollback returned the previous version to health: $failure"
    }
    throw
}
