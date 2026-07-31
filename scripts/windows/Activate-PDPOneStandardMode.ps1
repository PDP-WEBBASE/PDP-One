#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][string]$ApprovedCommit,
    [Parameter(Mandatory = $true)][string]$DeploymentId
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Restore-PDPOneEnvSetting([string]$Path, [string]$Name, $Value) {
    if ($null -eq $Value) {
        Set-PDPOneEnvValue -Path $Path -Name $Name -Value ""
    } else {
        Set-PDPOneEnvValue -Path $Path -Name $Name -Value ([string]$Value)
    }
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$markerPath = Join-Path $projectRoot "release\stable-mode.json"
if (-not (Test-Path -LiteralPath $markerPath)) { throw "Stable release marker is missing." }
$marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$marker.change_management_mode -ne "standard" -or [bool]$marker.trial_mode) {
    throw "Stable release marker does not request standard non-trial mode."
}
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$') { throw "Stable release commit is invalid." }
$backupReportPath = Join-Path $BackupPath "backup-report.json"
if (-not (Test-Path -LiteralPath $backupReportPath)) { throw "Stable release backup report is missing." }
$backupReport = Get-Content -LiteralPath $backupReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not [bool]$backupReport.restore_verified) { throw "Stable release activation requires a restore-verified backup." }
if ([string]$backupReport.approved_commit -ne $ApprovedCommit) { throw "Backup commit does not match stable release commit." }
if ([string]$backupReport.deployment_id -ne $DeploymentId) { throw "Backup deployment identifier does not match stable release deployment." }
if ([bool]$marker.require_external_backup -and (-not [bool]$backupReport.external_backup_copied)) {
    throw "Stable release activation requires a verified external backup mirror."
}

$previous = [ordered]@{
    PDP_CHANGE_MANAGEMENT_MODE = Get-PDPOneEnvValue -Path $envPath -Name "PDP_CHANGE_MANAGEMENT_MODE"
    PDP_TRIAL_MODE = Get-PDPOneEnvValue -Path $envPath -Name "PDP_TRIAL_MODE"
    PDP_EXTERNAL_BACKUP_ROOT = Get-PDPOneEnvValue -Path $envPath -Name "PDP_EXTERNAL_BACKUP_ROOT"
}
$externalRoot = [Environment]::ExpandEnvironmentVariables(([string]$marker.external_backup_root).Trim())
$driveRoot = [IO.Path]::GetPathRoot($externalRoot)
if ([bool]$marker.require_external_backup -and (-not $driveRoot -or -not (Test-Path -LiteralPath $driveRoot))) {
    throw "The approved external backup drive is not available."
}

try {
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_CHANGE_MANAGEMENT_MODE" -Value "standard"
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_TRIAL_MODE" -Value "false"
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_EXTERNAL_BACKUP_ROOT" -Value $externalRoot

    Set-Location $projectRoot
    Start-PDPOneRancherDesktop -TimeoutSeconds 300
    & docker compose --profile tunnel up --detach --force-recreate --no-build backend worker beat mcp web nginx tailscale
    if ($LASTEXITCODE -ne 0) { throw "Services could not be restarted in standard mode." }
    if (-not (Wait-PDPOneUrl -Url "http://127.0.0.1:8080/healthz" -TimeoutSeconds 180)) {
        throw "Local health did not recover after standard-mode activation."
    }
    $connectivity = & (Join-Path $projectRoot "scripts\windows\Repair-PDPOneConnectivity.ps1") -ProjectRoot $projectRoot -RepairAttempts 3
    if ($null -eq $connectivity -or [string]$connectivity.status -ne "succeeded") {
        throw "The stable public route could not be verified after standard-mode activation."
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts\windows\Test-PDPOne.ps1") -SkipChatGPTToolCheck
    if ($LASTEXITCODE -ne 0) { throw "Layered health failed after standard-mode activation." }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts\windows\Register-PDPOneStartupTask.ps1") -ProjectRoot $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Windows startup tasks could not be registered for the stable release." }

    $stateRoot = Join-Path $projectRoot "work\state"
    New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
    $statePath = Join-Path $stateRoot "stable-release.json"
    [ordered]@{
        schema = "pdp-one.stable-release-state.v1"
        release_version = [string]$marker.release_version
        activated_at = (Get-Date).ToUniversalTime().ToString("o")
        approved_commit = $ApprovedCommit
        deployment_id = $DeploymentId
        backup_id = [string]$backupReport.backup_id
        external_backup_path = [string]$backupReport.external_backup_path
        change_management_mode = "standard"
        trial_mode = $false
        database_restore_verified = [bool]$backupReport.restore_verified
        external_backup_verified = [bool]$backupReport.external_backup_copied
        startup_registered = $true
        local_health = $true
        public_health = $true
        token_rotated = $false
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8

    $agentRoot = Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT"
    if ([string]::IsNullOrWhiteSpace($agentRoot)) { $agentRoot = "C:\ProgramData\PDP-One\deployment-agent" }
    $agentState = Join-Path $agentRoot "state"
    New-Item -ItemType Directory -Force -Path $agentState | Out-Null
    Set-Content -LiteralPath (Join-Path $agentState "restart-agent-after-response") -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ASCII
    Write-Output $statePath
} catch {
    Restore-PDPOneEnvSetting -Path $envPath -Name "PDP_CHANGE_MANAGEMENT_MODE" -Value $previous.PDP_CHANGE_MANAGEMENT_MODE
    Restore-PDPOneEnvSetting -Path $envPath -Name "PDP_TRIAL_MODE" -Value $previous.PDP_TRIAL_MODE
    Restore-PDPOneEnvSetting -Path $envPath -Name "PDP_EXTERNAL_BACKUP_ROOT" -Value $previous.PDP_EXTERNAL_BACKUP_ROOT
    try {
        Set-Location $projectRoot
        & docker compose --profile tunnel up --detach --force-recreate --no-build backend worker beat mcp web nginx tailscale *> $null
    } catch { }
    throw
}
