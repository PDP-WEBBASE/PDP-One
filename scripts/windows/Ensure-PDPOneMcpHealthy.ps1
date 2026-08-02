#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$StableSeconds = 12
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

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

function Test-PDPOneDeploymentInProgress {
    $markerPath = "C:\ProgramData\PDP-One\deployment-agent\state\deployment-in-progress.json"
    if (-not (Test-Path -LiteralPath $markerPath)) { return $false }

    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $processId = 0
        [void][int]::TryParse([string]$marker.process_id, [ref]$processId)
        if ($processId -gt 0 -and $null -ne (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            return $true
        }

        Remove-Item -LiteralPath $markerPath -Force -ErrorAction SilentlyContinue
        return $false
    } catch {
        $file = Get-Item -LiteralPath $markerPath -ErrorAction SilentlyContinue
        if ($null -ne $file -and $file.LastWriteTimeUtc -lt [DateTime]::UtcNow.AddHours(-2)) {
            Remove-Item -LiteralPath $markerPath -Force -ErrorAction SilentlyContinue
            return $false
        }
        return $true
    }
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

if (Test-PDPOneDeploymentInProgress) { exit 0 }

$root = Get-InstallationRoot -RequestedRoot $ProjectRoot
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
    image_source = "configured_immutable_image"
    local_image_build_performed = $false
    source_files_modified = $false
    import_check = "pending"
    final_status = "failed"
    completed_at = $null
    volumes_touched = $false
    database_changed = $false
}

try {
    if (Test-PDPOneDeploymentInProgress) { exit 0 }

    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    & docker compose run --rm --no-deps --entrypoint python mcp -c "import server_procurement"
    if ($LASTEXITCODE -ne 0) { throw "Configured MCP image import verification failed." }
    $report.import_check = "passed"

    if (Test-PDPOneDeploymentInProgress) { exit 0 }

    & docker compose --profile tunnel up --detach --no-deps --no-build --pull never --force-recreate mcp
    if ($LASTEXITCODE -ne 0) { throw "MCP container recreation failed." }

    $deadline = (Get-Date).AddMinutes(2)
    do {
        if (Test-PDPOneDeploymentInProgress) { exit 0 }

        $current = Get-McpState
        if ($current.Status -eq "running") {
            Start-Sleep -Seconds ([Math]::Max(5, $StableSeconds))
            $confirmed = Get-McpState
            if ($confirmed.Status -eq "running" -and $confirmed.RestartCount -eq $current.RestartCount) {
                $report.final_status = "healthy"
                $report.completed_at = [DateTime]::UtcNow.ToString("o")
                $reportPath = Join-Path $root "PDP-ONE-MCP-SELF-HEAL-REPORT.json"
                $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
                exit 0
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "MCP container did not remain running."
} catch {
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = $_.Exception.Message
    $reportPath = Join-Path $root "PDP-ONE-MCP-SELF-HEAL-REPORT.json"
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    exit 1
}
