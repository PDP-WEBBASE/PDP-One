#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [int]$InitialTimeoutSeconds = 420,
    [int]$RecoveryTimeoutSeconds = 420,
    [int]$PollSeconds = 3
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$maintenanceRoot = "C:\ProgramData\PDP-One\maintenance"
New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
$reportPath = Join-Path $maintenanceRoot "rancher-startup-latest.json"

$report = [ordered]@{
    schema = "pdp-one.rancher-startup.v1"
    started_at = [DateTime]::UtcNow.ToString("o")
    completed_at = $null
    status = "failed"
    initial_timeout_seconds = $InitialTimeoutSeconds
    recovery_timeout_seconds = $RecoveryTimeoutSeconds
    initial_launch_attempted = $false
    bounded_restart_attempted = $false
    docker_ready = $false
    outcome = "pending"
    error = $null
}

function Wait-PDPOneDockerReady([int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PDPOneDockerEngine) { return $true }
        Start-Sleep -Seconds $PollSeconds
    }
    return [bool](Test-PDPOneDockerEngine)
}

function Get-PDPOneRancherExecutable {
    $candidates = @(
        "C:\Program Files\Rancher Desktop\Rancher Desktop.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Rancher Desktop\Rancher Desktop.exe")
    )
    return ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Invoke-PDPOneRancherLaunch {
    $script:report.initial_launch_attempted = $true
    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($rdctl) {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $rdctl.Source start --application.start-in-background --container-engine.name=moby --kubernetes.enabled=false *> $null
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
    }

    if (-not (Get-Process -Name "Rancher Desktop" -ErrorAction SilentlyContinue)) {
        $desktop = Get-PDPOneRancherExecutable
        if (-not $desktop) { throw "Rancher Desktop executable was not found." }
        Start-Process -FilePath $desktop -ArgumentList "--application.startInBackground=true" | Out-Null
    }
}

try {
    if (Test-PDPOneDockerEngine) {
        $report.status = "succeeded"
        $report.docker_ready = $true
        $report.outcome = "already_ready"
        $report.completed_at = [DateTime]::UtcNow.ToString("o")
        $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Write-Output $reportPath
        exit 0
    }

    Invoke-PDPOneRancherLaunch
    if (Wait-PDPOneDockerReady -TimeoutSeconds $InitialTimeoutSeconds) {
        $report.status = "succeeded"
        $report.docker_ready = $true
        $report.outcome = "ready_after_initial_launch"
        $report.completed_at = [DateTime]::UtcNow.ToString("o")
        $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Write-Output $reportPath
        exit 0
    }

    # Rancher can occasionally have a GUI/backend process after logon while the
    # Docker named pipe never appears. Perform one bounded non-destructive
    # restart through rdctl. This does not reset WSL, Rancher data, Docker
    # volumes, PostgreSQL data, Tailscale identity, or PDP One secrets.
    $report.bounded_restart_attempted = $true
    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($rdctl) {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $rdctl.Source shutdown *> $null
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
        Start-Sleep -Seconds 8
    }

    Invoke-PDPOneRancherLaunch
    if (-not (Wait-PDPOneDockerReady -TimeoutSeconds $RecoveryTimeoutSeconds)) {
        throw "Docker did not become ready after the bounded Rancher Desktop recovery cycle."
    }

    $report.status = "succeeded"
    $report.docker_ready = $true
    $report.outcome = "ready_after_bounded_restart"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    try { $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8 } catch { }
    throw $report.error
}
