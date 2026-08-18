#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$RepairAttempts = 2,
    [int]$PublicCheckTimeoutSeconds = 35,
    [int]$TransientConfirmDelaySeconds = 10,
    [int]$DnsPublicationTimeoutSeconds = 120,
    [int]$DnsPollIntervalSeconds = 10
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

function Wait-PDPOnePublicDnsPublication {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [int]$TimeoutSeconds = 120,
        [int]$PollIntervalSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds([Math]::Max(10, $TimeoutSeconds))
    do {
        $addresses = @(Get-PDPOnePublicIPv4Addresses -HostName $HostName)
        if ($addresses.Count -gt 0) { return $true }
        Start-Sleep -Seconds ([Math]::Max(2, $PollIntervalSeconds))
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Reset-PDPOneFunnelRegistration {
    Write-Host "The Funnel hostname is not published in public DNS. Resetting only the Funnel configuration and registering it again ..." -ForegroundColor Yellow
    $reset = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "exec", "-T", "tailscale", "tailscale", "--socket=/tmp/tailscaled.sock", "funnel", "reset") -FailureMessage "The stale Funnel configuration could not be reset." -IgnoreFailure -Quiet
    if ($reset.ExitCode -ne 0) { return $false }
    $register = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "exec", "-T", "tailscale", "tailscale", "--socket=/tmp/tailscaled.sock", "funnel", "--bg", "--yes", "80") -FailureMessage "The Funnel could not be registered again." -IgnoreFailure -Quiet
    return $register.ExitCode -eq 0
}

function Restart-PDPOnePublicRoute {
    Write-Host "Recreating nginx and Tailscale after a repeatedly confirmed full public-route failure ..." -ForegroundColor Yellow
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

function Complete-PDPOneConnectivityResult {
    param([string]$BaseUrl, $Checks, [string]$McpState)
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL" -Value $BaseUrl
    $result.status = "succeeded"
    $result.public_base_url = $BaseUrl
    $result.public_health_method = $Checks.Health.Method
    $result.public_api_health_method = $Checks.ApiHealth.Method
    $result.public_mcp_health_method = $Checks.McpHealth.Method
    $result.public_api_health = $(if ($Checks.ApiHealth.Success) { "healthy" } else { "failed" })
    $result.public_mcp_health = $McpState
    $result.local_dns_degraded = [bool]($Checks.Health.LocalDnsDegraded -or $Checks.ApiHealth.LocalDnsDegraded -or $Checks.McpHealth.LocalDnsDegraded)
    $result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
    return [pscustomobject]$result
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
    public_confirmation_count = 0
    public_dns_state = "pending"
    funnel_registration_reset = $false
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
    $candidateHost = ([Uri]$candidateUrl).Host

    # "Funnel on" is configuration state, not proof that the public hostname
    # has been published. A stale persisted Funnel configuration can survive a
    # reboot while public DNS returns NXDOMAIN. Wait for bounded publication,
    # then reset/re-register only Funnel once per startup run. This preserves
    # the Tailscale node identity, MCP token, nginx and all application data.
    if (-not (Wait-PDPOnePublicDnsPublication -HostName $candidateHost -TimeoutSeconds $DnsPublicationTimeoutSeconds -PollIntervalSeconds $DnsPollIntervalSeconds)) {
        $result.public_dns_state = "unpublished"
        if (-not $result.funnel_registration_reset) {
            $result.funnel_registration_reset = $true
            if (Reset-PDPOneFunnelRegistration) {
                if (Wait-PDPOnePublicDnsPublication -HostName $candidateHost -TimeoutSeconds $DnsPublicationTimeoutSeconds -PollIntervalSeconds $DnsPollIntervalSeconds) {
                    $result.public_dns_state = "published_after_funnel_reset"
                } else {
                    Write-Host "The Funnel registration was refreshed, but its hostname is still absent from public DNS." -ForegroundColor Yellow
                }
            }
        }
        if ($result.public_dns_state -eq "unpublished") {
            Start-Sleep -Seconds 3
            continue
        }
    } else {
        $result.public_dns_state = "published"
    }

    $checks = Test-PublicPdpEndpoints -BaseUrl $candidateUrl
    $result.public_confirmation_count = 1

    # Require three observations before any disruptive public-route repair.
    # A short external/DNS/Funnel wobble must not be amplified into a restart.
    if (-not $checks.Success) {
        $result.transient_failure_rechecked = $true
        foreach ($confirm in 1..2) {
            Start-Sleep -Seconds ([Math]::Max(5, $TransientConfirmDelaySeconds))
            $checks = Test-PublicPdpEndpoints -BaseUrl $candidateUrl
            $result.public_confirmation_count++
            if ($checks.Success) { break }
        }
    }

    if ($checks.Success) {
        return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "healthy"
    }

    # If public web + API are healthy while only the public MCP probe is
    # degraded, the Funnel and local nginx->MCP path are still intact. Do NOT
    # recreate nginx/Tailscale; preserve established ChatGPT connections and
    # let a later cycle observe whether the external MCP path recovered.
    if ($checks.Health.Success -and $checks.ApiHealth.Success -and -not $checks.McpHealth.Success) {
        Write-Host "Public web/API remain healthy while only the MCP probe is degraded; preserving the existing Funnel route." -ForegroundColor Yellow
        return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
    }

    if (-not $checks.Health.Success) {
        Write-Host "The public nginx health endpoint remained unavailable after three observations." -ForegroundColor Yellow
    } else {
        Write-Host "Public nginx is reachable but the public session API remained unavailable after three observations." -ForegroundColor Yellow
    }

    # Only a repeatedly confirmed full web/API public-route failure is allowed
    # to recreate nginx/Tailscale.
    if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
}

$result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
return [pscustomobject]$result
