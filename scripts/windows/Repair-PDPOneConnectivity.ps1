#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$RepairAttempts = 2,
    [int]$PublicCheckTimeoutSeconds = 35,
    [int]$TransientConfirmDelaySeconds = 5
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$mcpPathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
if ([string]::IsNullOrWhiteSpace($mcpPathToken)) { throw "PDP_MCP_PATH_TOKEN is missing." }

function Invoke-PDPOneConnectivityDockerCompose {
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

    $text = (($nativeOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
    if (-not $Quiet -and -not [string]::IsNullOrWhiteSpace($text)) {
        $safeText = ConvertTo-PDPOneRedactedText $text
        if (-not [string]::IsNullOrWhiteSpace($safeText)) { Write-Host $safeText }
    }
    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (docker compose exit code $exitCode)."
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Text = $text }
}

function Get-TailscaleStatus {
    $command = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "exec", "-T", "tailscale", "tailscale", "--socket=/tmp/tailscaled.sock", "status", "--json") -FailureMessage "Tailscale status could not be read." -IgnoreFailure -Quiet
    if ($command.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace([string]$command.Text)) { return $null }
    try { return ([string]$command.Text | ConvertFrom-Json) } catch { return $null }
}

function Get-FunnelStatusText {
    $command = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "exec", "-T", "tailscale", "tailscale", "--socket=/tmp/tailscaled.sock", "funnel", "status") -FailureMessage "Tailscale Funnel status could not be read." -IgnoreFailure -Quiet
    return [string]$command.Text
}

function Restart-PDPOnePublicRoute {
    Write-Host "Recreating nginx and Tailscale after confirmed public-route failure ..." -ForegroundColor Yellow
    $repair = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never", "--force-recreate", "nginx", "tailscale") -FailureMessage "The nginx/Tailscale route could not be recreated." -IgnoreFailure -Quiet
    Start-Sleep -Seconds 12
    return $repair.ExitCode -eq 0
}

function Test-PublicPdpEndpoints {
    param([string]$BaseUrl)
    $health = Test-PDPOnePublicHealth -Url "$BaseUrl/healthz" -TimeoutSeconds $PublicCheckTimeoutSeconds
    $apiHealth = Test-PDPOnePublicHealth -Url "$BaseUrl/api/v1/auth/session/" -ExpectedPattern '"authenticated"' -TimeoutSeconds $PublicCheckTimeoutSeconds
    $mcpHealth = Test-PDPOnePublicHealth -Url "$BaseUrl/mcp/$mcpPathToken/healthz" -ExpectedPattern "pdp-one-mcp" -TimeoutSeconds $PublicCheckTimeoutSeconds
    return [pscustomobject]@{
        Health = $health
        ApiHealth = $apiHealth
        McpHealth = $mcpHealth
        Success = [bool]($health.Success -and $apiHealth.Success -and $mcpHealth.Success)
    }
}

$result = [ordered]@{
    status = "failed"
    provider = "Tailscale Funnel (Docker)"
    public_base_url = $null
    local_api_health = "failed"
    local_mcp_health = "failed"
    public_health_method = $null
    public_api_health_method = $null
    public_mcp_health_method = $null
    public_api_health = "failed"
    public_mcp_health = "failed"
    local_dns_degraded = $false
    transient_failure_rechecked = $false
    repair_attempts = 0
    completed_at = $null
}

for ($attempt = 1; $attempt -le [Math]::Max(1, $RepairAttempts); $attempt++) {
    $result.repair_attempts = $attempt
    Write-Host "Connectivity repair attempt $attempt/$RepairAttempts ..." -ForegroundColor Cyan

    $startCommand = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never", "tailscale") -FailureMessage "The Tailscale container could not be started." -IgnoreFailure -Quiet
    if ($startCommand.ExitCode -ne 0) {
        Write-Host "The Tailscale container could not be started." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        continue
    }

    $localSessionUrl = "http://127.0.0.1:8080/api/v1/auth/session/"
    if (-not (Wait-PDPOneUrl -Url $localSessionUrl -TimeoutSeconds 25)) {
        Write-Host "The local nginx health shell is reachable, but the backend session API is not." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
        continue
    }
    $result.local_api_health = "healthy"

    $localMcpHealthUrl = "http://127.0.0.1:8080/mcp/$mcpPathToken/healthz"
    if (-not (Wait-PDPOneUrl -Url $localMcpHealthUrl -TimeoutSeconds 20)) {
        Write-Host "The local web/API path is healthy, but the token-bound MCP health route is not." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
        continue
    }
    $result.local_mcp_health = "healthy"

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

    $funnelCommand = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "exec", "-T", "tailscale", "tailscale", "--socket=/tmp/tailscaled.sock", "funnel", "--bg", "--yes", "80") -FailureMessage "Tailscale Funnel activation failed." -IgnoreFailure -Quiet
    $funnelExit = $funnelCommand.ExitCode
    $funnelOutput = [string]$funnelCommand.Text
    $funnelStatus = Get-FunnelStatusText
    $combined = $funnelOutput + [Environment]::NewLine + $funnelStatus
    $urlMatch = [regex]::Match($combined, 'https://[A-Za-z0-9.-]+\.ts\.net')
    $funnelConfirmed = $combined -match '(?i)Funnel on|Available on the internet|proxy http://127\.0\.0\.1:80'

    if (-not $urlMatch.Success -or (-not $funnelConfirmed -and $funnelExit -ne 0)) {
        Write-Host "Tailscale did not confirm an active Funnel." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) {
            Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "restart", "tailscale") -FailureMessage "Tailscale restart failed." -IgnoreFailure -Quiet | Out-Null
            Start-Sleep -Seconds 12
        }
        continue
    }

    $candidateUrl = $urlMatch.Value.TrimEnd('/')
    $checks = Test-PublicPdpEndpoints -BaseUrl $candidateUrl

    # A single network/DNS/Tailscale miss must not immediately recreate the route.
    # Confirm the same failure after a short delay before taking disruptive action.
    if (-not $checks.Success) {
        $result.transient_failure_rechecked = $true
        Start-Sleep -Seconds ([Math]::Max(2, $TransientConfirmDelaySeconds))
        $checks = Test-PublicPdpEndpoints -BaseUrl $candidateUrl
    }

    if ($checks.Success) {
        Set-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL" -Value $candidateUrl
        $result.status = "succeeded"
        $result.public_base_url = $candidateUrl
        $result.public_health_method = $checks.Health.Method
        $result.public_api_health_method = $checks.ApiHealth.Method
        $result.public_mcp_health_method = $checks.McpHealth.Method
        $result.public_api_health = "healthy"
        $result.public_mcp_health = "healthy"
        $result.local_dns_degraded = [bool]($checks.Health.LocalDnsDegraded -or $checks.ApiHealth.LocalDnsDegraded -or $checks.McpHealth.LocalDnsDegraded)
        $result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
        return [pscustomobject]$result
    }

    if (-not $checks.Health.Success) {
        Write-Host "Funnel is configured but the public nginx health endpoint failed twice." -ForegroundColor Yellow
    } elseif (-not $checks.ApiHealth.Success) {
        Write-Host "The public nginx health endpoint works, but the public session API failed twice." -ForegroundColor Yellow
    } else {
        Write-Host "Web/API are public, but the token-bound public MCP health route failed twice." -ForegroundColor Yellow
    }

    if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
}

$result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
return [pscustomobject]$result
