#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$RepairAttempts = 2,
    [int]$PublicCheckTimeoutSeconds = 35
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot

function Get-TailscaleStatus {
    $text = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock status --json 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($text)) { return $null }
    try { return ($text | ConvertFrom-Json) } catch { return $null }
}

function Get-FunnelStatusText {
    return (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel status 2>&1 | Out-String)
}

$result = [ordered]@{
    status = "failed"
    provider = "Tailscale Funnel (Docker)"
    public_base_url = $null
    public_health_method = $null
    local_dns_degraded = $false
    repair_attempts = 0
    completed_at = $null
}

for ($attempt = 1; $attempt -le [Math]::Max(1, $RepairAttempts); $attempt++) {
    $result.repair_attempts = $attempt
    Write-Host "Connectivity repair attempt $attempt/$RepairAttempts ..." -ForegroundColor Cyan

    & docker compose --profile tunnel up --detach --no-build tailscale
    if ($LASTEXITCODE -ne 0) {
        Write-Host "The Tailscale container could not be started." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        continue
    }

    $status = $null
    foreach ($wait in 1..30) {
        $status = Get-TailscaleStatus
        if ($null -ne $status) { break }
        Start-Sleep -Seconds 2
    }
    if ($null -eq $status -or [string]$status.BackendState -ne "Running") {
        Write-Host "Tailscale is not signed in or has not reached Running state." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        continue
    }

    $funnelOutput = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel --bg --yes 80 2>&1 | Out-String)
    $funnelExit = $LASTEXITCODE
    $funnelStatus = Get-FunnelStatusText
    $combined = $funnelOutput + [Environment]::NewLine + $funnelStatus
    $urlMatch = [regex]::Match($combined, 'https://[A-Za-z0-9.-]+\.ts\.net')
    $funnelConfirmed = $combined -match '(?i)Funnel on|Available on the internet|proxy http://127\.0\.0\.1:80'

    if (-not $urlMatch.Success -or (-not $funnelConfirmed -and $funnelExit -ne 0)) {
        Write-Host "Tailscale did not confirm an active Funnel." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) {
            & docker compose --profile tunnel restart tailscale *> $null
            Start-Sleep -Seconds 12
        }
        continue
    }

    $candidateUrl = $urlMatch.Value.TrimEnd('/')
    $health = Test-PDPOnePublicHealth -Url "$candidateUrl/healthz" -TimeoutSeconds $PublicCheckTimeoutSeconds
    if ($health.Success) {
        Set-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL" -Value $candidateUrl
        $result.status = "succeeded"
        $result.public_base_url = $candidateUrl
        $result.public_health_method = $health.Method
        $result.local_dns_degraded = [bool]$health.LocalDnsDegraded
        $result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
        return [pscustomobject]$result
    }

    Write-Host "Funnel is configured but the public health endpoint is not reachable yet." -ForegroundColor Yellow
    if ($attempt -lt $RepairAttempts) {
        & docker compose --profile tunnel restart tailscale *> $null
        Start-Sleep -Seconds 15
    }
}

$result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
return [pscustomobject]$result
