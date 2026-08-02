#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

function Get-InstallationRoot {
    $rootFile = Join-Path $env:LOCALAPPDATA 'PDP-One\installation-root.txt'
    if (Test-Path -LiteralPath $rootFile) {
        $saved = ([IO.File]::ReadAllText($rootFile)).Trim()
        if ($saved -and (Test-Path -LiteralPath (Join-Path $saved 'docker-compose.yml'))) {
            return (Resolve-Path -LiteralPath $saved).Path
        }
    }
    $current = (Get-Location).Path
    if (Test-Path -LiteralPath (Join-Path $current 'docker-compose.yml')) { return $current }
    throw 'PDP One installation root was not found.'
}

function Test-DockerReady {
    cmd.exe /d /c 'docker info >nul 2>&1'
    return $LASTEXITCODE -eq 0
}

function Start-DockerIfNeeded {
    if (Test-DockerReady) { return }
    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($rdctl) { & $rdctl.Source start --application.start-in-background *> $null }
    if (-not (Get-Process -Name 'Rancher Desktop' -ErrorAction SilentlyContinue)) {
        $candidates = @(
            'C:\Program Files\Rancher Desktop\Rancher Desktop.exe',
            (Join-Path $env:LOCALAPPDATA 'Programs\Rancher Desktop\Rancher Desktop.exe')
        )
        $desktop = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $desktop) { throw 'Rancher Desktop was not found.' }
        Start-Process -FilePath $desktop | Out-Null
    }
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) { return }
        Start-Sleep -Seconds 3
    }
    throw 'Docker did not become ready within five minutes.'
}

$root = Get-InstallationRoot
$dockerfile = Join-Path $root 'services\pdp_mcp\Dockerfile'
$toolFile = Join-Path $root 'services\pdp_mcp\procurement_analysis_tools.py'
if (-not (Test-Path -LiteralPath $dockerfile)) { throw 'MCP Dockerfile was not found.' }
if (-not (Test-Path -LiteralPath $toolFile)) { throw 'procurement_analysis_tools.py was not found in the deployed source.' }

$content = [IO.File]::ReadAllText($dockerfile)
if ($content -notmatch '(?m)^COPY .*procurement_analysis_tools\.py') {
    $pattern = '(?m)^COPY server\.py server_procurement\.py procurement_tools\.py automation_tools\.py deployment_queue\.py \.\s*$'
    $replacement = 'COPY server.py server_procurement.py procurement_tools.py procurement_analysis_tools.py automation_tools.py deployment_queue.py .'
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw 'The expected MCP Dockerfile COPY line was not found; no file was changed.'
    }
    $content = [regex]::Replace($content, $pattern, $replacement, 1)
    [IO.File]::WriteAllText($dockerfile, $content, [Text.UTF8Encoding]::new($false))
}

Start-DockerIfNeeded
Push-Location $root
try {
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' }

    & docker compose build mcp
    if ($LASTEXITCODE -ne 0) { throw 'MCP image build failed.' }

    & docker compose --profile tunnel up --detach --no-deps --force-recreate mcp
    if ($LASTEXITCODE -ne 0) { throw 'MCP container recreation failed.' }

    $deadline = (Get-Date).AddMinutes(2)
    do {
        $state = (& docker inspect --format '{{.State.Status}}' pdp-one-mcp-1 2>$null | Out-String).Trim()
        if ($state -eq 'running') {
            Start-Sleep -Seconds 4
            $state2 = (& docker inspect --format '{{.State.Status}}' pdp-one-mcp-1 2>$null | Out-String).Trim()
            if ($state2 -eq 'running') {
                Write-Host 'PDP One MCP repaired and running.' -ForegroundColor Green
                Write-Host 'No Docker volume or database data was changed.' -ForegroundColor Green
                exit 0
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    & docker compose logs --tail 120 mcp
    throw 'MCP did not remain running. The latest MCP logs are shown above.'
} finally {
    Pop-Location
}
