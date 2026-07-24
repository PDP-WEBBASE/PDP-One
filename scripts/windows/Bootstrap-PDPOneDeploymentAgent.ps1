#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [string]$TaskName = "PDP One Local Deployment Agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$sourcePath = Join-Path $PSScriptRoot "Invoke-PDPOneDeployment.ps1"
$targetPath = Join-Path $AgentRoot "bin\Invoke-PDPOneDeployment.ps1"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $AgentRoot "bootstrap-backups\$timestamp"
$backupPath = Join-Path $backupRoot "Invoke-PDPOneDeployment.ps1"
$desktop = [Environment]::GetFolderPath("Desktop")
$reportPath = Join-Path $desktop "PDP-ONE-AGENT-BOOTSTRAP-REPORT.json"
$taskWasRunning = $false
$backupCreated = $false

$report = [ordered]@{
    schema_version = 1
    operation = "bootstrap-deployment-agent-only"
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    completed_at = $null
    status = "starting"
    source_path = $sourcePath
    target_path = $targetPath
    source_sha256 = $null
    installed_sha256 = $null
    previous_sha256 = $null
    backup_path = $null
    scheduled_task = $TaskName
    scheduled_task_state = $null
    application_changed = $false
    docker_changed = $false
    database_changed = $false
    volumes_changed = $false
    backups_changed = $false
    tailscale_changed = $false
    token_changed = $false
    error = $null
}

function Save-Report {
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

function Assert-PowerShellFile([string]$Path) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        $messages = ($errors | ForEach-Object { $_.Message }) -join "; "
        throw "PowerShell parse validation failed: $messages"
    }
}

Save-Report

try {
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Bootstrap source file is missing: $sourcePath"
    }
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $targetPath))) {
        throw "Installed deployment-agent bin directory does not exist."
    }

    $processingRoot = Join-Path $AgentRoot "queue\processing"
    if (Test-Path -LiteralPath $processingRoot) {
        $activeRequests = @(Get-ChildItem -LiteralPath $processingRoot -File -ErrorAction SilentlyContinue)
        if ($activeRequests.Count -gt 0) {
            throw "A deployment-agent request is currently processing. Bootstrap was not started."
        }
    }

    Assert-PowerShellFile -Path $sourcePath
    $sourceText = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8
    foreach ($marker in @("Invoke-PDPOneAcquisitionRetry", "acquiring-approved-source", "production_changed")) {
        if ($sourceText -notmatch [regex]::Escape($marker)) {
            throw "Bootstrap source does not contain required marker: $marker"
        }
    }

    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.source_sha256 = $sourceHash

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $taskWasRunning = $task.State -eq "Running"

    if (Test-Path -LiteralPath $targetPath) {
        New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
        Copy-Item -LiteralPath $targetPath -Destination $backupPath -Force
        $backupCreated = $true
        $report.backup_path = $backupPath
        $report.previous_sha256 = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    } else {
        throw "Installed deployment script is missing: $targetPath"
    }

    Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Start-Sleep -Seconds 2

    $temporaryPath = "$targetPath.new"
    Copy-Item -LiteralPath $sourcePath -Destination $temporaryPath -Force
    Assert-PowerShellFile -Path $temporaryPath
    $temporaryHash = (Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($temporaryHash -ne $sourceHash) {
        throw "Staged bootstrap file hash does not match the source hash."
    }

    Move-Item -LiteralPath $temporaryPath -Destination $targetPath -Force
    Assert-PowerShellFile -Path $targetPath
    $installedHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($installedHash -ne $sourceHash) {
        throw "Installed deployment script hash verification failed."
    }

    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Start-Sleep -Seconds 3
    $finalTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop

    $report.status = "succeeded"
    $report.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    $report.installed_sha256 = $installedHash
    $report.scheduled_task_state = [string]$finalTask.State
    Save-Report

    Write-Host "Deployment Agent bootstrap completed successfully." -ForegroundColor Green
    Write-Host "Report: $reportPath" -ForegroundColor Cyan
    exit 0
} catch {
    $message = $_.Exception.Message
    try {
        Remove-Item -LiteralPath "$targetPath.new" -Force -ErrorAction SilentlyContinue
        if ($backupCreated -and (Test-Path -LiteralPath $backupPath)) {
            Copy-Item -LiteralPath $backupPath -Destination $targetPath -Force
        }
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    } catch {
        $message = "$message | Local rollback warning: $($_.Exception.Message)"
    }

    $report.status = "failed"
    $report.completed_at = (Get-Date).ToUniversalTime().ToString("o")
    $report.error = $message
    try {
        $report.scheduled_task_state = [string](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    } catch { }
    Save-Report

    Write-Host "Deployment Agent bootstrap failed. The previous script was restored when possible." -ForegroundColor Red
    Write-Host "Report: $reportPath" -ForegroundColor Yellow
    exit 1
}
