#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param([int]$DockerTimeoutSeconds = 300, [int]$HealthTimeoutSeconds = 180)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

try {
    $ProjectRoot = Get-PDPOneProjectRoot
    Set-Location $ProjectRoot
    Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds
    $null = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
    if (-not (Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot)) {
        throw "The MCP path token changed outside the approved rotation workflow. Startup was stopped."
    }
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    Write-Host "Starting existing PDP One services without build, pull, migration, or token rotation ..." -ForegroundColor Cyan
    & docker compose --profile tunnel up --detach --no-build
    if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start." }

    $tailscaleStatus = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock status --json 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0 -or $tailscaleStatus -notmatch '"BackendState"\s*:\s*"Running"') {
        throw "Tailscale is not signed in. Run CONNECT-CHATGPT.bat once to complete sign-in."
    }
    & docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel --bg --yes 80 *> $null
    $funnelStatus = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel status 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0 -or $funnelStatus -notmatch '(?i)Funnel on|Available on the internet|proxy http://127\.0\.0\.1:80') {
        throw "Tailscale Funnel did not become active."
    }
    if (-not (Wait-PDPOneUrl -Url "http://127.0.0.1:8080/healthz" -TimeoutSeconds $HealthTimeoutSeconds)) {
        throw "PDP One local health check timed out."
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOne.ps1") -SkipChatGPTToolCheck
    if ($LASTEXITCODE -ne 0) { throw "Layered health check failed." }
    Write-Host "PDP One is healthy. Existing MCP settings were preserved." -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneDiagnostics.ps1") -FailureMessage $_.Exception.Message
    exit 1
}
