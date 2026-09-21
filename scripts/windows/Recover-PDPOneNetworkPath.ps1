#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$LocalCheckTimeoutSeconds = 8
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location $ProjectRoot

$maintenanceRoot = "C:\ProgramData\PDP-One\maintenance"
New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
$reportPath = Join-Path $maintenanceRoot "network-recovery-latest.json"
$report = [ordered]@{
    schema = "pdp-one.network-recovery.v1"
    checked_at = [DateTime]::UtcNow.ToString("o")
    docker_ready = $false
    local_health = $false
    local_api = $false
    local_mcp = $false
    action = "pending"
    status = "failed"
    delegated_to_stable_startup = $false
    error = $null
}

function Test-PDPOneFastUrl([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $LocalCheckTimeoutSeconds
        return [bool]($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

try {
    $report.docker_ready = [bool](Test-PDPOneDockerEngine)
    if (-not $report.docker_ready) {
        $report.action = "stable_startup"
        $report.delegated_to_stable_startup = $true
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Start-PDPOne.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Stable startup could not recover the unavailable Docker/runtime path." }
        $report.status = "succeeded"
        $report.checked_at = [DateTime]::UtcNow.ToString("o")
        Write-PDPOneJsonFile -Path $reportPath -Value $report
        Write-Output $reportPath
        exit 0
    }

    $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
    $mcpPathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"

    $report.local_health = Test-PDPOneFastUrl "http://127.0.0.1:8080/healthz"
    $report.local_api = Test-PDPOneFastUrl "http://127.0.0.1:8080/api/v1/auth/session/"
    $report.local_mcp = Test-PDPOneFastUrl "http://127.0.0.1:8080/mcp/$mcpPathToken/healthz"

    if (-not ($report.local_health -and $report.local_api -and $report.local_mcp)) {
        $report.action = "stable_startup"
        $report.delegated_to_stable_startup = $true
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Start-PDPOne.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Stable startup could not recover the local PDP One path." }
    } else {
        # A Windows network-profile event must not run the full Rancher/Compose
        # startup path when local Docker, nginx, API and MCP are already healthy.
        # Repair only the public edge and preserve all running containers.
        $report.action = "public_connectivity_only"
        $result = & (Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1") -ProjectRoot $ProjectRoot -RepairAttempts 1
        if ($null -eq $result -or [string]$result.status -ne "succeeded") {
            throw "Bounded public connectivity recovery did not converge."
        }
    }

    $report.status = "succeeded"
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    Write-PDPOneJsonFile -Path $reportPath -Value $report
    Write-Output $reportPath
} catch {
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    try { Write-PDPOneJsonFile -Path $reportPath -Value $report } catch { }
    throw $report.error
}
