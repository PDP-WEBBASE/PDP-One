#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$StableSeconds = 12,
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.OperationLock.ps1")

function Get-InstallationRoot {
    param([string]$RequestedRoot)
    if ($RequestedRoot -and (Test-Path -LiteralPath (Join-Path $RequestedRoot "docker-compose.yml"))) {
        return (Resolve-Path -LiteralPath $RequestedRoot).Path
    }
    $rootFile = Join-Path $env:LOCALAPPDATA "PDP-One\installation-root.txt"
    if (Test-Path -LiteralPath $rootFile) {
        $saved = ([IO.File]::ReadAllText($rootFile)).Trim()
        if ($saved -and (Test-Path -LiteralPath (Join-Path $saved "docker-compose.yml"))) {
            return (Resolve-Path -LiteralPath $saved).Path
        }
    }
    if (Test-Path -LiteralPath "C:\PDP-One\docker-compose.yml") { return "C:\PDP-One" }
    throw "PDP One installation root was not found."
}

function Test-DockerReady {
    cmd.exe /d /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Get-McpState {
    $containerId = (& docker compose ps -q mcp 2>$null | Out-String).Trim()
    if (-not $containerId) {
        return [pscustomobject]@{ Id = ""; Status = "missing"; RestartCount = 0; Health = "missing" }
    }
    $status = (& docker inspect --format "{{.State.Status}}" $containerId 2>$null | Out-String).Trim()
    $health = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" $containerId 2>$null | Out-String).Trim()
    $restartCountText = (& docker inspect --format "{{.RestartCount}}" $containerId 2>$null | Out-String).Trim()
    $restartCount = 0
    [void][int]::TryParse($restartCountText, [ref]$restartCount)
    return [pscustomobject]@{ Id = $containerId; Status = $status; RestartCount = $restartCount; Health = $health }
}

function Write-McpReport {
    param([string]$Root, $Report)
    $reportPath = Join-Path $Root "PDP-ONE-MCP-SELF-HEAL-REPORT.json"
    $Report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

function Test-LocalMcpRoute {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 8
        $body = ConvertTo-PDPOneResponseText $response.Content
        return $response.StatusCode -eq 200 -and $body -match 'pdp-one-mcp'
    } catch {
        return $false
    }
}

$root = Get-InstallationRoot -RequestedRoot $ProjectRoot
$deploymentOperation = Read-PDPOneDeploymentOperation -AgentRoot $AgentRoot -RemoveStale
if ($deploymentOperation.Active) {
    $skipped = [ordered]@{
        operation = "mcp-self-heal"
        started_at = [DateTime]::UtcNow.ToString("o")
        completed_at = [DateTime]::UtcNow.ToString("o")
        final_status = "skipped_deployment_in_progress"
        deployment_in_progress = $true
        deployment_id = [string]$deploymentOperation.State.deployment_id
        protected_target_commit = [string]$deploymentOperation.State.target_commit
        local_image_build_performed = $false
        volumes_touched = $false
        database_changed = $false
    }
    Write-McpReport -Root $root -Report $skipped
    exit 0
}

if (-not (Test-DockerReady)) { exit 0 }
Set-Location $root
$envPath = Assert-PDPOneConfiguration -ProjectRoot $root
$mcpPathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
$localMcpHealthUrl = "http://127.0.0.1:8080/mcp/$mcpPathToken/healthz"
$confirmedPublicFailure = $false
$publicConnectivity = $null

$state = Get-McpState
if ($state.Status -eq "running" -and $state.Health -eq "healthy") {
    Start-Sleep -Seconds ([Math]::Max(3, $StableSeconds))
    $second = Get-McpState
    if ($second.Status -eq "running" -and $second.Health -eq "healthy" -and $second.RestartCount -eq $state.RestartCount) {
        if (Test-LocalMcpRoute -Url $localMcpHealthUrl) {
            # The five-minute watchdog owns bounded persistent public-MCP recovery.
            # RepairAttempts=1 means this path can never force-recreate nginx or
            # Tailscale for a broad route failure. It may only observe/reset state,
            # repair unpublished DNS, or perform the thresholded Funnel-only refresh.
            $publicConnectivity = & (Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1") -ProjectRoot $root -RepairAttempts 1 -AllowPersistentMcpEscalation -AgentRoot $AgentRoot
            if ($null -ne $publicConnectivity -and [string]$publicConnectivity.status -eq "succeeded") {
                if ([string]$publicConnectivity.public_mcp_health -eq "healthy") { exit 0 }
                if ([string]$publicConnectivity.public_mcp_health -eq "degraded") { $confirmedPublicFailure = $true }
            }
        }
    }
}

$report = [ordered]@{
    operation = "mcp-self-heal"
    started_at = [DateTime]::UtcNow.ToString("o")
    initial_status = $state.Status
    initial_health = $state.Health
    initial_restart_count = $state.RestartCount
    deployment_in_progress = $false
    import_check = "pending"
    local_route_health = "failed"
    public_route_health = $(if ($confirmedPublicFailure) { "degraded_observed" } else { "not_checked" })
    route_repair_performed = $false
    funnel_registration_reset = $(if ($null -ne $publicConnectivity) { [bool]$publicConnectivity.funnel_registration_reset } else { $false })
    persistent_mcp_failure_count = $(if ($null -ne $publicConnectivity) { [int]$publicConnectivity.persistent_mcp_failure_count } else { 0 })
    funnel_repair_cooldown_remaining = $(if ($null -ne $publicConnectivity) { [int]$publicConnectivity.funnel_repair_cooldown_remaining } else { 0 })
    container_recreated = $false
    final_status = "failed"
    completed_at = $null
    local_image_build_performed = $false
    image_pull_performed = $false
    volumes_touched = $false
    database_changed = $false
}

try {
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    if ($state.Status -eq "running" -and $state.Health -eq "healthy" -and $confirmedPublicFailure -and (Test-LocalMcpRoute -Url $localMcpHealthUrl)) {
        $report.import_check = "not_required_container_healthy"
        $report.local_route_health = "healthy"
        $report.public_route_health = "degraded_observed"
        $report.route_repair_performed = [bool]$report.funnel_registration_reset
        $report.final_status = $(if ($report.funnel_registration_reset) { "healthy_local_public_degraded_after_bounded_funnel_refresh" } else { "healthy_local_public_degraded_observed" })
        $report.completed_at = [DateTime]::UtcNow.ToString("o")
        Write-McpReport -Root $root -Report $report
        exit 0
    }

    # If the process/container itself is healthy but the LOCAL route is broken,
    # route repair is appropriate. Do not recreate a healthy MCP container.
    if ($state.Status -eq "running" -and $state.Health -eq "healthy") {
        $report.import_check = "not_required_container_healthy"
        $report.route_repair_performed = $true
        $connectivity = & (Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1") -ProjectRoot $root -RepairAttempts 2 -AgentRoot $AgentRoot
        if ($null -ne $connectivity -and [string]$connectivity.status -eq "succeeded" -and (Test-LocalMcpRoute -Url $localMcpHealthUrl)) {
            $report.local_route_health = "healthy"
            $report.public_route_health = [string]$connectivity.public_mcp_health
            $report.final_status = "healthy_after_route_repair"
            $report.completed_at = [DateTime]::UtcNow.ToString("o")
            Write-McpReport -Root $root -Report $report
            exit 0
        }
        throw "MCP container is healthy but the token-bound MCP route remains unavailable after route repair."
    }

    & docker compose run --rm --no-deps --no-build --pull never --entrypoint python mcp -c "import server_procurement"
    if ($LASTEXITCODE -ne 0) { throw "Existing MCP image import verification failed." }
    $report.import_check = "passed"

    & docker compose --profile tunnel up --detach --no-deps --no-build --pull never --force-recreate mcp
    if ($LASTEXITCODE -ne 0) { throw "MCP container recreation failed." }
    $report.container_recreated = $true

    $deadline = (Get-Date).AddMinutes(2)
    do {
        $current = Get-McpState
        if ($current.Status -eq "running" -and $current.Health -eq "healthy") {
            Start-Sleep -Seconds ([Math]::Max(5, $StableSeconds))
            $confirmed = Get-McpState
            if ($confirmed.Status -eq "running" -and $confirmed.Health -eq "healthy" -and $confirmed.RestartCount -eq $current.RestartCount) {
                if (-not (Test-LocalMcpRoute -Url $localMcpHealthUrl)) {
                    $report.route_repair_performed = $true
                    $connectivity = & (Join-Path $PSScriptRoot "Repair-PDPOneConnectivity.ps1") -ProjectRoot $root -RepairAttempts 2 -AgentRoot $AgentRoot
                    if ($null -eq $connectivity -or [string]$connectivity.status -ne "succeeded") {
                        throw "MCP container recovered but the token-bound route could not be repaired."
                    }
                    $report.public_route_health = [string]$connectivity.public_mcp_health
                }
                if (-not (Test-LocalMcpRoute -Url $localMcpHealthUrl)) {
                    throw "MCP container is healthy but its local token-bound route is still unavailable."
                }
                $report.local_route_health = "healthy"
                $report.final_status = "healthy"
                $report.completed_at = [DateTime]::UtcNow.ToString("o")
                Write-McpReport -Root $root -Report $report
                exit 0
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "MCP container did not become Docker-healthy and stable."
} catch {
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    Write-McpReport -Root $root -Report $report
    exit 1
}
