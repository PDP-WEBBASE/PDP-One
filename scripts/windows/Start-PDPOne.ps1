#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [int]$DockerTimeoutSeconds = 300,
    [int]$HealthTimeoutSeconds = 180,
    [switch]$OpenLocalPage,
    [switch]$ForceTunnelRepair
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$mutex = New-Object Threading.Mutex($false, "Global\PDP-One-Stable-Startup")
if (-not $mutex.WaitOne(0)) { exit 0 }
$ProjectRoot = $null
$report = [ordered]@{
    operation = "stable-startup"
    started_at = (Get-Date).ToUniversalTime().ToString('o')
    completed_at = $null
    status = "failed"
    docker = "pending"
    local_health = "pending"
    public_health = "pending"
    public_health_method = $null
    local_dns_degraded = $false
    token_continuity = "pending"
    diagnostics = $null
}

try {
    $ProjectRoot = Get-PDPOneProjectRoot
    Set-Location $ProjectRoot
    Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds
    $report.docker = "ready"
    $null = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
    if (-not (Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot)) {
        throw "The MCP path token changed outside the approved rotation workflow. Startup was stopped."
    }
    $report.token_continuity = "verified"

    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    Write-Host "Starting existing PDP One services without build, pull, migration, or token rotation ..." -ForegroundColor Cyan
    & docker compose --profile tunnel up --detach --no-build
    if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start." }

    if (-not (Wait-PDPOneUrl -Url "http://127.0.0.1:8080/healthz" -TimeoutSeconds $HealthTimeoutSeconds)) {
        throw "PDP One local health check timed out."
    }
    $report.local_health = "healthy"

    if ($OpenLocalPage) {
        Start-Process "http://localhost:8080" | Out-Null
    }

    $repairAttempts = $(if ($ForceTunnelRepair) { 3 } else { 2 })
    $connectivity = & (Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1") -ProjectRoot $ProjectRoot -RepairAttempts $repairAttempts
    if ($null -eq $connectivity -or [string]$connectivity.status -ne "succeeded") {
        throw "The local application is healthy, but the stable public Tailscale route could not be verified."
    }
    $report.public_health = "healthy"
    $report.public_health_method = [string]$connectivity.public_health_method
    $report.local_dns_degraded = [bool]$connectivity.local_dns_degraded

    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOne.ps1") -SkipChatGPTToolCheck
    if ($LASTEXITCODE -ne 0) { throw "Layered health check failed." }

    $report.status = "succeeded"
    $report.completed_at = (Get-Date).ToUniversalTime().ToString('o')
    $reportDir = Join-Path $ProjectRoot "work\reports"
    Write-PDPOneJsonFile -Path (Join-Path $reportDir "startup-latest.json") -Value $report
    Write-PDPOneJsonFile -Path (Join-Path $ProjectRoot "PDP-ONE-LAST-STARTUP-REPORT.json") -Value $report
    Write-Host "PDP One is healthy. Existing MCP settings, data and Docker volumes were preserved." -ForegroundColor Green
    if ($report.local_dns_degraded) {
        Write-Host "The public route is healthy through public IPv4 resolution. The local browser was opened on localhost so Windows DNS settings do not need to change." -ForegroundColor Yellow
    }
} catch {
    $failure = $_.Exception.Message
    $report.completed_at = (Get-Date).ToUniversalTime().ToString('o')
    if ($ProjectRoot) {
        $diagnosticPath = [string](& (Join-Path $PSScriptRoot "New-PDPOneDiagnostics.ps1") -FailureMessage $failure -Stage "startup" | Select-Object -Last 1)
        $report.diagnostics = $diagnosticPath
        Write-PDPOneJsonFile -Path (Join-Path $ProjectRoot "PDP-ONE-LAST-STARTUP-REPORT.json") -Value $report
    }
    Write-Host $failure -ForegroundColor Red
    exit 1
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
