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
    if (-not $containerId) { return [pscustomobject]@{ Id = ""; Status = "missing"; RestartCount = 0 } }
    $status = (& docker inspect --format "{{.State.Status}}" $containerId 2>$null | Out-String).Trim()
    $restartCountText = (& docker inspect --format "{{.RestartCount}}" $containerId 2>$null | Out-String).Trim()
    $restartCount = 0
    [void][int]::TryParse($restartCountText, [ref]$restartCount)
    return [pscustomobject]@{ Id = $containerId; Status = $status; RestartCount = $restartCount }
}

function Write-McpReport {
    param([string]$Root, $Report)
    $reportPath = Join-Path $Root "PDP-ONE-MCP-SELF-HEAL-REPORT.json"
    $Report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
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

$state = Get-McpState
if ($state.Status -eq "running") {
    Start-Sleep -Seconds ([Math]::Max(3, $StableSeconds))
    $second = Get-McpState
    if ($second.Status -eq "running" -and $second.RestartCount -eq $state.RestartCount) { exit 0 }
}

$report = [ordered]@{
    operation = "mcp-self-heal"
    started_at = [DateTime]::UtcNow.ToString("o")
    initial_status = $state.Status
    initial_restart_count = $state.RestartCount
    deployment_in_progress = $false
    import_check = "pending"
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

    & docker compose run --rm --no-deps --no-build --pull never --entrypoint python mcp -c "import server_procurement"
    if ($LASTEXITCODE -ne 0) { throw "Existing MCP image import verification failed." }
    $report.import_check = "passed"

    & docker compose --profile tunnel up --detach --no-deps --no-build --pull never --force-recreate mcp
    if ($LASTEXITCODE -ne 0) { throw "MCP container recreation failed." }

    $deadline = (Get-Date).AddMinutes(2)
    do {
        $current = Get-McpState
        if ($current.Status -eq "running") {
            Start-Sleep -Seconds ([Math]::Max(5, $StableSeconds))
            $confirmed = Get-McpState
            if ($confirmed.Status -eq "running" -and $confirmed.RestartCount -eq $current.RestartCount) {
                $report.final_status = "healthy"
                $report.completed_at = [DateTime]::UtcNow.ToString("o")
                Write-McpReport -Root $root -Report $report
                exit 0
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "MCP container did not remain running."
} catch {
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = $_.Exception.Message
    Write-McpReport -Root $root -Report $report
    exit 1
}
