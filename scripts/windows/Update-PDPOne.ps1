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
    [switch]$AgentAuthorized,
    [switch]$DevelopmentFastMode
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

function Invoke-PDPOneDocker {
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
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& docker @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if (-not $Quiet -and $nativeOutput.Count -gt 0) {
        $nativeText = ConvertTo-PDPOneRedactedText (($nativeOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if (-not [string]::IsNullOrWhiteSpace($nativeText)) { Write-Host $nativeText }
    }

    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (docker exit code $exitCode)."
    }
    return $exitCode
}

function Invoke-PDPOneSequentialBuild {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Service)

    Start-PDPOneRancherDesktop -TimeoutSeconds 600
    if (-not (Test-PDPOneDockerEngine)) {
        throw "Docker Engine is not ready before building $Service. Production was not modified."
    }

    Write-Host "Building isolated candidate image: $Service" -ForegroundColor Cyan
    $exitCode = Invoke-PDPOneDockerCompose -Arguments @("build", $Service) -FailureMessage "Updated $Service image could not be built." -IgnoreFailure
    if ($exitCode -ne 0) {
        if (-not (Test-PDPOneDockerEngine)) {
            throw "Docker Engine became unavailable while building $Service. Production was not modified."
        }
        throw "Updated $Service image could not be built (docker compose exit code $exitCode)."
    }

    if (-not (Test-PDPOneDockerEngine)) {
        throw "Docker Engine became unavailable after building $Service. Production was not modified."
    }
}

function Set-PDPOneProcessEnvironment([string]$Name, $Value) {
    if ($null -eq $Value) {
        Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue
    } else {
        Set-Item ("Env:" + $Name) ([string]$Value)
    }
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
    if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or -not $DeploymentId -or -not $CodeArchive -or (-not $DevelopmentFastMode -and -not $BackupPath)) {
        throw "Agent-authorized update is missing its locked commit, deployment, or rollback snapshot."
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

$backupReport = $null
if (-not $DevelopmentFastMode) {
    $backupReport = Get-Content -LiteralPath (Join-Path $BackupPath "backup-report.json") -Raw | ConvertFrom-Json
    if (-not $backupReport.restore_verified) { throw "Update is blocked: the linked backup has not passed restore verification." }
}

$releaseSuffix = $(if ($ApprovedCommit -match '^[0-9a-f]{40}$') { $ApprovedCommit.Substring(0, 12) } else { (Get-Date).ToString("yyyyMMddHHmm") })
$candidateImages = [ordered]@{
    backend = "pdp-one-backend:candidate-$releaseSuffix"
    mcp = "pdp-one-mcp:candidate-$releaseSuffix"
    web = "pdp-one-web:candidate-$releaseSuffix"
}
$productionImages = [ordered]@{
    backend = "pdp-one-backend:local"
    mcp = "pdp-one-mcp:local"
    web = "pdp-one-web:local"
}
$previousEnvironment = @{
    COMPOSE_PARALLEL_LIMIT = $env:COMPOSE_PARALLEL_LIMIT
    PDP_BACKEND_IMAGE = $env:PDP_BACKEND_IMAGE
    PDP_MCP_IMAGE = $env:PDP_MCP_IMAGE
    PDP_WEB_IMAGE = $env:PDP_WEB_IMAGE
}

$migrationAttempted = $false
$productionTouched = $false
$sourceEnvPath = Join-Path $SourceRoot ".env"
try {
    # The candidate images are built one at a time while the current production
    # containers and their active image tags remain untouched. The shared backend
    # candidate is reused by backend, worker and beat.
    Copy-Item -LiteralPath $envPath -Destination $sourceEnvPath -Force
    $env:COMPOSE_PARALLEL_LIMIT = "1"
    $env:PDP_BACKEND_IMAGE = $candidateImages.backend
    $env:PDP_MCP_IMAGE = $candidateImages.mcp
    $env:PDP_WEB_IMAGE = $candidateImages.web
    Set-Location $SourceRoot
    Invoke-PDPOneDockerCompose -Arguments @("config", "--quiet") -FailureMessage "Approved Docker Compose configuration is invalid." | Out-Null
    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneSequentialBuild -Service $service
    }

    Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue
    foreach ($name in @("COMPOSE_PARALLEL_LIMIT", "PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) {
        Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name]
    }

    Set-Location $InstalledRoot
    Invoke-PDPOneDockerCompose -Arguments @("--profile", "tunnel", "stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale") -FailureMessage "Application services could not be stopped cleanly." | Out-Null
    $productionTouched = $true

    & robocopy.exe $SourceRoot $InstalledRoot /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Approved application files could not be copied." }

    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneDocker -Arguments @("image", "tag", $candidateImages[$service], $productionImages[$service]) -FailureMessage "Candidate $service image could not be activated." | Out-Null
    }

    Invoke-PDPOneDockerCompose -Arguments @("config", "--quiet") -FailureMessage "Updated Docker Compose configuration is invalid." | Out-Null
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

    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneDocker -Arguments @("image", "rm", $candidateImages[$service]) -FailureMessage "Candidate image tag cleanup failed." -IgnoreFailure -Quiet | Out-Null
    }

    # Space maintenance is intentionally non-transactional and runs only after
    # the release is healthy. It never prunes Docker volumes. A maintenance
    # failure is recorded as a warning and must not roll back a healthy release.
    try {
        $maintenanceArgs = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $InstalledRoot "scripts\windows\Invoke-PDPOneDiskMaintenance.ps1"),
            "-Mode", "post-deployment",
            "-KeepLocalFinalBackups", "2"
        )
        if (-not $DevelopmentFastMode) { $maintenanceArgs += @("-ProtectedBackupPath", $BackupPath) }
        $maintenanceOutput = @(& powershell.exe @maintenanceArgs)
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
    $rollbackCode = 0
    $rollbackResult = "not-required"

    if ($productionTouched) {
        Write-Host "Update failed. Starting automatic rollback ..." -ForegroundColor Red
        $rollbackArgs = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $PSScriptRoot "Rollback-PDPOne.ps1"),
            "-BackupPath", $BackupPath,
            "-CodeArchive", $CodeArchive,
            "-Automatic"
        )
        if ($migrationAttempted -and -not $DevelopmentFastMode) { $rollbackArgs += "-RestoreDatabase" }
        & powershell.exe @rollbackArgs
        $rollbackCode = $LASTEXITCODE
        $rollbackResult = $(if ($rollbackCode -eq 0) { "healthy" } else { "failed" })
    }

    $diagnosticDeploymentId = $(if ([string]::IsNullOrWhiteSpace($DeploymentId)) { "manual-update" } else { $DeploymentId })
    $diagnosticBackupId = $(if ($DevelopmentFastMode) { "development-fast-no-database-backup" } elseif ($null -ne $backupReport -and -not [string]::IsNullOrWhiteSpace([string]$backupReport.backup_id)) { [string]$backupReport.backup_id } else { "unknown-backup" })
    $diagnosticArgs = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "New-PDPOneDiagnostics.ps1"),
        "-FailureMessage", $failure,
        "-DeploymentId", $diagnosticDeploymentId,
        "-BackupId", $diagnosticBackupId,
        "-RollbackResult", $rollbackResult,
        "-Stage", $(if ($productionTouched) { "update" } else { "prebuild" })
    )
    & powershell.exe @diagnosticArgs

    if ($productionTouched) {
        if ($rollbackCode -ne 0) { throw "Update failed and automatic rollback also failed: $failure" }
        throw "Update failed; automatic rollback returned the previous version to health: $failure"
    }
    throw "Release image build failed before production was modified: $failure"
} finally {
    Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue
    foreach ($name in @("COMPOSE_PARALLEL_LIMIT", "PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) {
        Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name]
    }
    Set-Location $InstalledRoot
}
