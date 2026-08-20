#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$RepairAttempts = 2,
    [int]$PublicCheckTimeoutSeconds = 35,
    [int]$TransientConfirmDelaySeconds = 10,
    [int]$DnsPublicationTimeoutSeconds = 60,
    [int]$DnsPollIntervalSeconds = 10,
    [switch]$AllowPersistentMcpEscalation,
    [int]$McpOnlyFailureThreshold = 2,
    [int]$FunnelRepairCooldownSeconds = 900,
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.OperationLock.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$mcpPathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
if ([string]::IsNullOrWhiteSpace($mcpPathToken)) { throw "PDP_MCP_PATH_TOKEN is missing." }
$configuredAgentRoot = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT")
if (-not [string]::IsNullOrWhiteSpace($configuredAgentRoot)) {
    $AgentRoot = ($configuredAgentRoot -replace '/', '\')
}
$connectivityReportDir = Join-Path $AgentRoot "reports"
$connectivityReportPath = Join-Path $connectivityReportDir "public-mcp-connectivity.json"

function New-PDPOnePublicMcpConnectivityState {
    return [ordered]@{
        schema = "pdp-one.public-mcp-connectivity.v1"
        checked_at = (Get-Date).ToUniversalTime().ToString('o')
        status = "unknown"
        local_mcp = "unknown"
        public_web = "unknown"
        public_api = "unknown"
        public_mcp = "unknown"
        dns_state = "unknown"
        consecutive_mcp_only_failures = 0
        last_funnel_repair_at = $null
        last_funnel_repair_result = "never"
        cooldown_seconds_remaining = 0
        repair_suppressed_deployment = $false
        confirmation_count = 0
    }
}

function Read-PDPOnePublicMcpConnectivityState {
    $state = New-PDPOnePublicMcpConnectivityState
    if (-not (Test-Path -LiteralPath $connectivityReportPath)) { return $state }
    try {
        $raw = Get-Content -LiteralPath $connectivityReportPath -Raw | ConvertFrom-Json
        if ($null -eq $raw -or [string]$raw.schema -ne "pdp-one.public-mcp-connectivity.v1") { return $state }
        foreach ($name in @(
            "checked_at", "status", "local_mcp", "public_web", "public_api", "public_mcp", "dns_state",
            "consecutive_mcp_only_failures", "last_funnel_repair_at", "last_funnel_repair_result",
            "cooldown_seconds_remaining", "repair_suppressed_deployment", "confirmation_count"
        )) {
            if ($null -ne $raw.PSObject.Properties[$name]) { $state[$name] = $raw.$name }
        }
    } catch { }
    return $state
}

function Get-PDPOneFunnelRepairCooldownRemaining {
    param($State)
    [DateTimeOffset]$lastRepair = [DateTimeOffset]::MinValue
    if ([string]::IsNullOrWhiteSpace([string]$State.last_funnel_repair_at)) { return 0 }
    if (-not [DateTimeOffset]::TryParse([string]$State.last_funnel_repair_at, [ref]$lastRepair)) { return 0 }
    $elapsed = [int]([DateTimeOffset]::UtcNow - $lastRepair.ToUniversalTime()).TotalSeconds
    return [Math]::Max(0, [Math]::Max(0, $FunnelRepairCooldownSeconds) - $elapsed)
}

function Write-PDPOnePublicMcpConnectivityState {
    param($State)
    try {
        New-Item -ItemType Directory -Force -Path $connectivityReportDir | Out-Null
        $State.checked_at = (Get-Date).ToUniversalTime().ToString('o')
        $State.cooldown_seconds_remaining = Get-PDPOneFunnelRepairCooldownRemaining -State $State
        $json = $State | ConvertTo-Json -Depth 5
        $temporary = "$connectivityReportPath.tmp"
        [IO.File]::WriteAllText($temporary, $json, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $connectivityReportPath -Force
    } catch { }
}

function Set-PDPOneConnectivityObservation {
    param(
        [string]$Status,
        [string]$LocalMcp,
        [string]$PublicWeb,
        [string]$PublicApi,
        [string]$PublicMcp,
        [string]$DnsState,
        [int]$ConfirmationCount,
        [switch]$ResetMcpOnlyFailures
    )
    $state = Read-PDPOnePublicMcpConnectivityState
    $state.status = $Status
    $state.local_mcp = $LocalMcp
    $state.public_web = $PublicWeb
    $state.public_api = $PublicApi
    $state.public_mcp = $PublicMcp
    $state.dns_state = $DnsState
    $state.confirmation_count = $ConfirmationCount
    $state.repair_suppressed_deployment = $false
    if ($ResetMcpOnlyFailures) { $state.consecutive_mcp_only_failures = 0 }
    Write-PDPOnePublicMcpConnectivityState -State $state
    return $state
}

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
        [int]$TimeoutSeconds = 60,
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
    param([string]$Reason = "public connectivity repair")
    Write-Host "Refreshing only the Funnel registration after $Reason ..." -ForegroundColor Yellow
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
    persistent_mcp_escalation = [bool]$AllowPersistentMcpEscalation
    persistent_mcp_failure_count = 0
    funnel_repair_cooldown_remaining = 0
    repair_suppressed_deployment = $false
    repair_attempts = 0
    completed_at = $null
}

for ($attempt = 1; $attempt -le [Math]::Max(1, $RepairAttempts); $attempt++) {
    $result.repair_attempts = $attempt
    Write-Host "Connectivity repair attempt $attempt/$RepairAttempts ..." -ForegroundColor Cyan

    $startCommand = Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never", "tailscale") -FailureMessage "The Tailscale container could not be started." -IgnoreFailure -Quiet
    if ($startCommand.ExitCode -ne 0) {
        [void](Set-PDPOneConnectivityObservation -Status "tailscale_unavailable" -LocalMcp "unknown" -PublicWeb "unknown" -PublicApi "unknown" -PublicMcp "unknown" -DnsState "unknown" -ConfirmationCount 0 -ResetMcpOnlyFailures)
        Write-Host "The Tailscale container could not be started." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        continue
    }

    $localSessionUrl = "http://127.0.0.1:8080/api/v1/auth/session/"
    if (-not (Wait-PDPOneUrl -Url $localSessionUrl -TimeoutSeconds 25)) {
        [void](Set-PDPOneConnectivityObservation -Status "local_api_failed" -LocalMcp "unknown" -PublicWeb "unknown" -PublicApi "unknown" -PublicMcp "unknown" -DnsState "unknown" -ConfirmationCount 0 -ResetMcpOnlyFailures)
        Write-Host "The local nginx health shell is reachable, but the backend session API is not." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
        continue
    }
    $result.local_api_health = "healthy"

    $localMcpHealthUrl = "http://127.0.0.1:8080/mcp/$mcpPathToken/healthz"
    if (-not (Wait-PDPOneUrl -Url $localMcpHealthUrl -TimeoutSeconds 20)) {
        [void](Set-PDPOneConnectivityObservation -Status "local_mcp_failed" -LocalMcp "failed" -PublicWeb "unknown" -PublicApi "unknown" -PublicMcp "unknown" -DnsState "unknown" -ConfirmationCount 0 -ResetMcpOnlyFailures)
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
        [void](Set-PDPOneConnectivityObservation -Status "tailscale_not_running" -LocalMcp "healthy" -PublicWeb "unknown" -PublicApi "unknown" -PublicMcp "unknown" -DnsState "unknown" -ConfirmationCount 0 -ResetMcpOnlyFailures)
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
        [void](Set-PDPOneConnectivityObservation -Status "funnel_not_confirmed" -LocalMcp "healthy" -PublicWeb "unknown" -PublicApi "unknown" -PublicMcp "unknown" -DnsState "unknown" -ConfirmationCount 0 -ResetMcpOnlyFailures)
        Write-Host "Tailscale did not confirm an active Funnel." -ForegroundColor Yellow
        if ($attempt -lt $RepairAttempts) {
            Invoke-PDPOneConnectivityDockerCompose -Arguments @("--profile", "tunnel", "restart", "tailscale") -FailureMessage "Tailscale restart failed." -IgnoreFailure -Quiet | Out-Null
            Start-Sleep -Seconds 12
        }
        continue
    }

    $candidateUrl = $urlMatch.Value.TrimEnd('/')
    $candidateHost = ([Uri]$candidateUrl).Host

    if (-not (Wait-PDPOnePublicDnsPublication -HostName $candidateHost -TimeoutSeconds $DnsPublicationTimeoutSeconds -PollIntervalSeconds $DnsPollIntervalSeconds)) {
        $result.public_dns_state = "unpublished"
        if (-not $result.funnel_registration_reset) {
            $result.funnel_registration_reset = $true
            if (Reset-PDPOneFunnelRegistration -Reason "unpublished public DNS") {
                if (Wait-PDPOnePublicDnsPublication -HostName $candidateHost -TimeoutSeconds $DnsPublicationTimeoutSeconds -PollIntervalSeconds $DnsPollIntervalSeconds) {
                    $result.public_dns_state = "published_after_funnel_reset"
                } else {
                    Write-Host "The Funnel registration was refreshed, but its hostname is still absent from public DNS." -ForegroundColor Yellow
                }
            }
        }
        if ($result.public_dns_state -eq "unpublished") {
            [void](Set-PDPOneConnectivityObservation -Status "dns_unpublished" -LocalMcp "healthy" -PublicWeb "failed" -PublicApi "failed" -PublicMcp "failed" -DnsState "unpublished" -ConfirmationCount 0 -ResetMcpOnlyFailures)
            Start-Sleep -Seconds 3
            continue
        }
    } else {
        $result.public_dns_state = "published"
    }

    $checks = Test-PublicPdpEndpoints -BaseUrl $candidateUrl
    $result.public_confirmation_count = 1

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
        [void](Set-PDPOneConnectivityObservation -Status "healthy" -LocalMcp "healthy" -PublicWeb "healthy" -PublicApi "healthy" -PublicMcp "healthy" -DnsState $result.public_dns_state -ConfirmationCount $result.public_confirmation_count -ResetMcpOnlyFailures)
        return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "healthy"
    }

    if ($checks.Health.Success -and $checks.ApiHealth.Success -and -not $checks.McpHealth.Success) {
        $escalationMutex = New-Object Threading.Mutex($false, "Global\PDP-One-Public-Mcp-Funnel-Repair")
        $escalationLock = $false
        try {
            try { $escalationLock = $escalationMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $escalationLock = $true }
            if (-not $escalationLock) {
                Write-Host "Another bounded public MCP repair cycle is already evaluating the Funnel; preserving the route." -ForegroundColor Yellow
                return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
            }

            $state = Read-PDPOnePublicMcpConnectivityState
            $state.status = "public_mcp_degraded"
            $state.local_mcp = "healthy"
            $state.public_web = "healthy"
            $state.public_api = "healthy"
            $state.public_mcp = "degraded"
            $state.dns_state = $result.public_dns_state
            $state.confirmation_count = $result.public_confirmation_count
            $state.repair_suppressed_deployment = $false
            $state.cooldown_seconds_remaining = Get-PDPOneFunnelRepairCooldownRemaining -State $state

            if (-not $AllowPersistentMcpEscalation) {
                $state.status = "public_mcp_degraded_observed"
                $result.persistent_mcp_failure_count = [int]$state.consecutive_mcp_only_failures
                $result.funnel_repair_cooldown_remaining = [int]$state.cooldown_seconds_remaining
                Write-PDPOnePublicMcpConnectivityState -State $state
                Write-Host "Public web/API remain healthy while only MCP is degraded; this observer does not advance the persistent-failure counter." -ForegroundColor Yellow
                return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
            }

            $state.consecutive_mcp_only_failures = [Math]::Max(0, [int]$state.consecutive_mcp_only_failures) + 1
            $result.persistent_mcp_failure_count = [int]$state.consecutive_mcp_only_failures
            $result.funnel_repair_cooldown_remaining = [int]$state.cooldown_seconds_remaining

            $deploymentOperation = Read-PDPOneDeploymentOperation -AgentRoot $AgentRoot -RemoveStale
            if ($deploymentOperation.Active) {
                $state.status = "public_mcp_degraded_deployment_suppressed"
                $state.repair_suppressed_deployment = $true
                $result.repair_suppressed_deployment = $true
                Write-PDPOnePublicMcpConnectivityState -State $state
                Write-Host "Public MCP remains degraded, but Funnel repair is suppressed while an exact deployment is active." -ForegroundColor Yellow
                return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
            }

            $threshold = [Math]::Max(2, $McpOnlyFailureThreshold)
            if ([int]$state.consecutive_mcp_only_failures -lt $threshold -or [int]$state.cooldown_seconds_remaining -gt 0) {
                Write-PDPOnePublicMcpConnectivityState -State $state
                Write-Host "Public web/API remain healthy while only MCP is degraded; waiting for the bounded persistent-failure threshold/cooldown before Funnel refresh." -ForegroundColor Yellow
                return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
            }

            $state.last_funnel_repair_at = (Get-Date).ToUniversalTime().ToString('o')
            $state.last_funnel_repair_result = "started"
            $state.status = "funnel_refresh_in_progress"
            Write-PDPOnePublicMcpConnectivityState -State $state
            $result.funnel_registration_reset = $true

            $resetSucceeded = Reset-PDPOneFunnelRegistration -Reason "persistent public MCP-only degradation"
            if ($resetSucceeded) {
                [void](Wait-PDPOnePublicDnsPublication -HostName $candidateHost -TimeoutSeconds $DnsPublicationTimeoutSeconds -PollIntervalSeconds $DnsPollIntervalSeconds)
                Start-Sleep -Seconds 5
                $afterRepair = Test-PublicPdpEndpoints -BaseUrl $candidateUrl
                if ($afterRepair.Success) {
                    $state.status = "healthy_after_funnel_refresh"
                    $state.public_web = "healthy"
                    $state.public_api = "healthy"
                    $state.public_mcp = "healthy"
                    $state.consecutive_mcp_only_failures = 0
                    $state.last_funnel_repair_result = "succeeded"
                    $state.confirmation_count = 1
                    Write-PDPOnePublicMcpConnectivityState -State $state
                    return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $afterRepair -McpState "healthy"
                }
            }

            $state.status = "public_mcp_degraded_after_funnel_refresh"
            $state.last_funnel_repair_result = "failed"
            $state.public_mcp = "degraded"
            Write-PDPOnePublicMcpConnectivityState -State $state
            Write-Host "The bounded Funnel refresh completed but public MCP is still degraded; preserving identity, tokens and local services for the next cooldown cycle." -ForegroundColor Yellow
            return Complete-PDPOneConnectivityResult -BaseUrl $candidateUrl -Checks $checks -McpState "degraded"
        } finally {
            if ($escalationLock) { $escalationMutex.ReleaseMutex() }
            $escalationMutex.Dispose()
        }
    }

    [void](Set-PDPOneConnectivityObservation -Status "broader_public_route_failure" -LocalMcp "healthy" -PublicWeb $(if ($checks.Health.Success) { "healthy" } else { "failed" }) -PublicApi $(if ($checks.ApiHealth.Success) { "healthy" } else { "failed" }) -PublicMcp $(if ($checks.McpHealth.Success) { "healthy" } else { "failed" }) -DnsState $result.public_dns_state -ConfirmationCount $result.public_confirmation_count -ResetMcpOnlyFailures)

    if (-not $checks.Health.Success) {
        Write-Host "The public nginx health endpoint remained unavailable after three observations." -ForegroundColor Yellow
    } else {
        Write-Host "Public nginx is reachable but the public session API remained unavailable after three observations." -ForegroundColor Yellow
    }

    if ($attempt -lt $RepairAttempts) { [void](Restart-PDPOnePublicRoute) }
}

$result.completed_at = (Get-Date).ToUniversalTime().ToString('o')
return [pscustomobject]$result
