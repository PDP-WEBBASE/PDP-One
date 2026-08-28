#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [int]$IncidentFailureThreshold = 3,
    [int]$RepairCooldownSeconds = 900
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
$configuredAgentRoot = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT")
if (-not [string]::IsNullOrWhiteSpace($configuredAgentRoot)) { $AgentRoot = ($configuredAgentRoot -replace '/', '\') }

$observerRoot = Join-Path $AgentRoot "reports\mcp-route-observability"
$latestPath = Join-Path $observerRoot "latest.json"
$watchdogReportPath = Join-Path $AgentRoot "reports\public-edge-watchdog.json"
$watchdogStatePath = Join-Path $AgentRoot "state\public-edge-watchdog.json"
$connectivityPath = Join-Path $AgentRoot "reports\public-mcp-connectivity.json"
$repairScript = Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1"
$observerScript = Join-Path $PSScriptRoot "Observe-PDPOneMcpRoute.ps1"
New-Item -ItemType Directory -Force -Path (Split-Path $watchdogReportPath -Parent), (Split-Path $watchdogStatePath -Parent) | Out-Null

function Write-JsonAtomic {
    param([string]$Path, $Value)
    $temporary = "$Path.tmp"
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function New-WatchdogReport {
    [ordered]@{
        schema = "pdp-one.public-edge-watchdog.v1"
        checked_at = [DateTime]::UtcNow.ToString("o")
        status = "unknown"
        observer_available = $false
        observer_age_seconds = $null
        active_incident = $null
        consecutive_failures = 0
        root_cause_classification = "unknown"
        local_runtime_healthy = $false
        public_edge_failed = $false
        local_funnel_to_nginx_healthy = $false
        public_edge_externalized = $false
        repair_attempted = $false
        repair_stage = "none"
        repair_actions = 0
        repair_suppressed_deployment = $false
        cooldown_seconds_remaining = 0
        final_public_mcp = "unknown"
        stable_status_refreshed = $false
        secrets_included = $false
        token_rotated = $false
        tailscale_identity_reset = $false
        database_changed = $false
        docker_volumes_touched = $false
        error = $null
    }
}

function Read-WatchdogState {
    $state = [ordered]@{ last_repair_at=$null; last_incident=$null; last_result="never" }
    if (-not (Test-Path -LiteralPath $watchdogStatePath)) { return $state }
    try {
        $raw = Get-Content -LiteralPath $watchdogStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($key in @('last_repair_at','last_incident','last_result')) {
            if ($null -ne $raw.PSObject.Properties[$key]) { $state[$key] = $raw.$key }
        }
    } catch { }
    return $state
}

function Get-CooldownRemaining {
    param($State)
    if ([string]::IsNullOrWhiteSpace([string]$State.last_repair_at)) { return 0 }
    [DateTimeOffset]$last = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse([string]$State.last_repair_at, [ref]$last)) { return 0 }
    $elapsed = [int]([DateTimeOffset]::UtcNow - $last.ToUniversalTime()).TotalSeconds
    return [Math]::Max(0, [Math]::Max(0,$RepairCooldownSeconds) - $elapsed)
}

function Get-CheckpointStatus {
    param($Sample, [string]$Id)
    $match = @($Sample.checkpoints | Where-Object { [string]$_.id -eq $Id } | Select-Object -First 1)
    if ($match.Count -eq 0) { return "missing" }
    return [string]$match[0].status
}

function Test-LocalFunnelToNginx {
    $output = @()
    $exitCode = -1
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& docker compose --profile tunnel exec -T tailscale sh -lc "wget -q -O- http://127.0.0.1:80/healthz" 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $text = (($output | ForEach-Object { [string]$_ }) -join "`n")
    return [bool]($exitCode -eq 0 -and $text -match 'PDP One ready')
}

function Update-StableHealthyConnectivityStatus {
    param($Sample)
    if ((Get-CheckpointStatus -Sample $Sample -Id 'CP-05') -ne 'pass') { return $false }
    if ((Get-CheckpointStatus -Sample $Sample -Id 'CP-08') -ne 'pass') { return $false }
    if ((Get-CheckpointStatus -Sample $Sample -Id 'CP-09') -ne 'pass') { return $false }
    if ((Get-CheckpointStatus -Sample $Sample -Id 'CP-10') -ne 'pass') { return $false }

    $publicBase = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
    if ([string]::IsNullOrWhiteSpace($publicBase)) { return $false }
    try {
        $api = Invoke-WebRequest -UseBasicParsing -Uri ($publicBase.TrimEnd('/') + '/api/v1/auth/session/') -TimeoutSec 8
        if ($api.StatusCode -ne 200 -or [string]$api.Content -notmatch '"authenticated"') { return $false }
    } catch { return $false }

    $previous = $null
    if (Test-Path -LiteralPath $connectivityPath) {
        try { $previous = Get-Content -LiteralPath $connectivityPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $previous = $null }
    }
    $lastRepairAt = $null
    $lastRepairResult = "never"
    $cooldown = 0
    if ($previous) {
        if ($null -ne $previous.PSObject.Properties['last_funnel_repair_at']) { $lastRepairAt = $previous.last_funnel_repair_at }
        if ($null -ne $previous.PSObject.Properties['last_funnel_repair_result']) { $lastRepairResult = [string]$previous.last_funnel_repair_result }
        if ($null -ne $previous.PSObject.Properties['cooldown_seconds_remaining']) { $cooldown = [Math]::Max(0,[int]$previous.cooldown_seconds_remaining) }
    }
    $connectivity = [ordered]@{
        schema = 'pdp-one.public-mcp-connectivity.v1'
        checked_at = [DateTime]::UtcNow.ToString('o')
        status = 'healthy'
        local_mcp = 'healthy'
        public_web = 'healthy'
        public_api = 'healthy'
        public_mcp = 'healthy'
        dns_state = 'published'
        consecutive_mcp_only_failures = 0
        last_funnel_repair_at = $lastRepairAt
        last_funnel_repair_result = $lastRepairResult
        cooldown_seconds_remaining = $cooldown
        repair_suppressed_deployment = $false
        confirmation_count = 1
    }
    Write-JsonAtomic -Path $connectivityPath -Value $connectivity
    return $true
}

$report = New-WatchdogReport
$mutex = $null
$mutexHeld = $false
try {
    if (-not (Test-Path -LiteralPath $latestPath)) {
        $report.status = "observer_missing"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $sample = Get-Content -LiteralPath $latestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$sample.schema -ne "pdp-one.mcp-route-observability.v2") {
        $report.status = "observer_schema_mismatch"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $observedAt = [DateTimeOffset]::Parse([string]$sample.observed_at)
    $observerAge = [Math]::Max(0, [int]([DateTimeOffset]::UtcNow - $observedAt.ToUniversalTime()).TotalSeconds)
    $report.observer_available = $true
    $report.observer_age_seconds = $observerAge
    $report.active_incident = [string]$sample.active_incident
    $report.consecutive_failures = [int]$sample.consecutive_failures
    $report.root_cause_classification = [string]$sample.root_cause_classification

    if ($observerAge -gt 180) {
        $report.status = "observer_stale"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $localIds = @('CP-01','CP-02','CP-03','CP-04','CP-05','CP-12','CP-13')
    $publicIds = @('CP-06','CP-07','CP-08','CP-09','CP-10')
    $localHealthy = $true
    foreach ($id in $localIds) {
        if ((Get-CheckpointStatus -Sample $sample -Id $id) -ne 'pass') { $localHealthy = $false; break }
    }
    $publicFailed = $false
    foreach ($id in $publicIds) {
        if ((Get-CheckpointStatus -Sample $sample -Id $id) -eq 'fail') { $publicFailed = $true; break }
    }
    $report.local_runtime_healthy = $localHealthy
    $report.public_edge_failed = $publicFailed

    if (-not $localHealthy) {
        $report.status = "local_runtime_failure_not_edge_repaired"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    if (-not $publicFailed) {
        $report.stable_status_refreshed = [bool](Update-StableHealthyConnectivityStatus -Sample $sample)
    }

    if (-not $publicFailed -or [string]::IsNullOrWhiteSpace([string]$sample.active_incident) -or [int]$sample.consecutive_failures -lt [Math]::Max(1,$IncidentFailureThreshold)) {
        $report.status = "healthy_or_not_confirmed"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $deploymentOperation = Read-PDPOneDeploymentOperation -AgentRoot $AgentRoot -RemoveStale
    if ($deploymentOperation.Active) {
        $report.status = "repair_suppressed_deployment"
        $report.repair_suppressed_deployment = $true
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $state = Read-WatchdogState
    $cooldown = Get-CooldownRemaining -State $state
    $report.cooldown_seconds_remaining = $cooldown
    if ($cooldown -gt 0 -and [string]$state.last_incident -eq [string]$sample.active_incident) {
        $report.status = "incident_in_cooldown"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $mutex = New-Object Threading.Mutex($false, "Global\PDP-One-Public-Edge-V3")
    try { $mutexHeld = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $mutexHeld = $true }
    if (-not $mutexHeld) {
        $report.status = "another_edge_repair_active"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $report.repair_attempted = $true
    $report.repair_stage = "soft_reconcile"
    $report.repair_actions = 1
    $soft = & $repairScript -ProjectRoot $ProjectRoot -RepairAttempts 1 -AllowPersistentMcpEscalation -AgentRoot $AgentRoot
    if ($null -ne $soft -and [string]$soft.status -eq 'succeeded' -and [string]$soft.public_mcp_health -eq 'healthy') {
        $report.status = "recovered_after_soft_reconcile"
        $report.final_public_mcp = "healthy"
        $state.last_repair_at = [DateTime]::UtcNow.ToString("o")
        $state.last_incident = [string]$sample.active_incident
        $state.last_result = "soft_reconcile_succeeded"
        Write-JsonAtomic -Path $watchdogStatePath -Value $state
        if (Test-Path -LiteralPath $observerScript) { & $observerScript -ProjectRoot $ProjectRoot | Out-Null }
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    if ($null -ne $soft -and [string]$soft.status -eq 'succeeded' -and [string]$soft.public_mcp_health -eq 'degraded') {
        $report.status = "mcp_only_degradation_delegated_to_existing_watchdog"
        $report.final_public_mcp = "degraded"
        Write-JsonAtomic -Path $watchdogReportPath -Value $report
        Write-Output $watchdogReportPath
        exit 0
    }

    $daemonPass = (Get-CheckpointStatus -Sample $sample -Id 'CP-06') -eq 'pass'
    $funnelPass = (Get-CheckpointStatus -Sample $sample -Id 'CP-07') -eq 'pass'
    $dnsPass = (Get-CheckpointStatus -Sample $sample -Id 'CP-08') -eq 'pass'
    $publicWebFail = (Get-CheckpointStatus -Sample $sample -Id 'CP-09') -eq 'fail'
    $publicMcpFail = (Get-CheckpointStatus -Sample $sample -Id 'CP-10') -eq 'fail'
    if ($daemonPass -and $funnelPass -and $dnsPass -and $publicWebFail -and $publicMcpFail) {
        $localFunnelHealthy = Test-LocalFunnelToNginx
        $report.local_funnel_to_nginx_healthy = $localFunnelHealthy
        if ($localFunnelHealthy) {
            $report.status = "tailscale_public_edge_failure"
            $report.root_cause_classification = "TAILSCALE_PUBLIC_EDGE_FAILURE"
            $report.public_edge_externalized = $true
            $report.repair_stage = "public_edge_observe_only"
            $report.final_public_mcp = "failed"
            $state.last_repair_at = [DateTime]::UtcNow.ToString("o")
            $state.last_incident = [string]$sample.active_incident
            $state.last_result = "tailscale_public_edge_failure_observed"
            Write-JsonAtomic -Path $watchdogStatePath -Value $state
            if (Test-Path -LiteralPath $observerScript) { & $observerScript -ProjectRoot $ProjectRoot | Out-Null }
            Write-JsonAtomic -Path $watchdogReportPath -Value $report
            Write-Output $watchdogReportPath
            exit 0
        }
    }

    $report.repair_stage = "bounded_edge_recreate"
    $report.repair_actions = 2
    $bounded = & $repairScript -ProjectRoot $ProjectRoot -RepairAttempts 2 -AgentRoot $AgentRoot
    $state.last_repair_at = [DateTime]::UtcNow.ToString("o")
    $state.last_incident = [string]$sample.active_incident
    if ($null -ne $bounded -and [string]$bounded.status -eq 'succeeded' -and [string]$bounded.public_mcp_health -eq 'healthy') {
        $report.status = "recovered_after_bounded_edge_recreate"
        $report.final_public_mcp = "healthy"
        $state.last_result = "bounded_edge_recreate_succeeded"
    } else {
        $report.status = "repair_failed_preserved_identity"
        $report.final_public_mcp = $(if ($null -ne $bounded) { [string]$bounded.public_mcp_health } else { "failed" })
        $state.last_result = "failed"
    }
    Write-JsonAtomic -Path $watchdogStatePath -Value $state
    if (Test-Path -LiteralPath $observerScript) { & $observerScript -ProjectRoot $ProjectRoot | Out-Null }
    Write-JsonAtomic -Path $watchdogReportPath -Value $report
    Write-Output $watchdogReportPath
} catch {
    $report.status = "watchdog_error"
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    Write-JsonAtomic -Path $watchdogReportPath -Value $report
    Write-Output $watchdogReportPath
    exit 0
} finally {
    if ($mutexHeld -and $null -ne $mutex) { try { $mutex.ReleaseMutex() } catch { } }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
