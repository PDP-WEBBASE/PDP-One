#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Test-DockerEngine {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Find-InstalledProjectRoot {
    $containerId = docker ps -a `
        --filter "label=com.docker.compose.project=pdp-one" `
        --filter "label=com.docker.compose.service=nginx" `
        --format "{{.ID}}" 2>$null | Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "The existing PDP One installation was not found. Run INSTALL-PDP-ONE.bat first."
    }

    $inspectOutput = docker inspect $containerId
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect the existing PDP One installation." }
    $inspect = @($inspectOutput | ConvertFrom-Json)[0]
    $workingDirectory = $inspect.Config.Labels.'com.docker.compose.project.working_dir'

    if ([string]::IsNullOrWhiteSpace($workingDirectory) -or -not (Test-Path -LiteralPath $workingDirectory)) {
        throw "The installed PDP One project folder could not be found."
    }
    return (Resolve-Path -LiteralPath $workingDirectory).Path
}

function Copy-ApplicationFiles([string]$From, [string]$To) {
    if ($From -eq $To) { return }

    Write-Host "Copying the new application version while preserving settings and data ..." -ForegroundColor Cyan
    $arguments = @(
        $From,
        $To,
        "/E",
        "/COPY:DAT",
        "/DCOPY:DAT",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NP",
        "/XF", ".env", "pdp-one-diagnostics.txt",
        "/XD", ".git", ".sites-runtime", "node_modules", ".next", "dist", "outputs", "work"
    )
    & robocopy @arguments | Out-Host
    if ($LASTEXITCODE -gt 7) { throw "Application files could not be copied. Robocopy exit code: $LASTEXITCODE" }
}

function New-RandomSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Ensure-TrialConnectionSettings([string]$Path) {
    $content = [IO.File]::ReadAllText($Path)
    if ($content -notmatch '(?m)^PDP_MCP_PATH_TOKEN=') {
        $content = $content.TrimEnd() + "`r`nPDP_MCP_PATH_TOKEN=$(New-RandomSecret 32)`r`n"
    }
    if ($content -notmatch '(?m)^PDP_TRIAL_MODE=') {
        $content = $content.TrimEnd() + "`r`nPDP_TRIAL_MODE=true`r`n"
    }
    if ($content -notmatch '(?m)^PDP_TRIAL_ADMIN_USERNAME=') {
        $content = $content.TrimEnd() + "`r`nPDP_TRIAL_ADMIN_USERNAME=pdp-admin`r`n"
    }
    if ($content -notmatch '(?m)^PDP_TRIAL_ADMIN_PASSWORD=') {
        $content = $content.TrimEnd() + "`r`nPDP_TRIAL_ADMIN_PASSWORD=$(New-RandomSecret 24)`r`n"
    }
    [IO.File]::WriteAllText($Path, $content, [Text.UTF8Encoding]::new($false))
}

Write-Host "PDP One automatic updater" -ForegroundColor Green
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is unavailable. Start Rancher Desktop and try again."
}
if (-not (Test-DockerEngine)) {
    throw "The container engine is not ready. Open Rancher Desktop, wait until Moby is running, then try again."
}

$InstalledRoot = Find-InstalledProjectRoot
if (-not (Test-Path -LiteralPath (Join-Path $InstalledRoot ".env"))) {
    throw "The existing secure .env configuration was not found. The update stopped without changing the installation."
}

Copy-ApplicationFiles -From $SourceRoot -To $InstalledRoot
Set-Location $InstalledRoot
Ensure-TrialConnectionSettings -Path (Join-Path $InstalledRoot ".env")

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid. The existing data was not deleted." }

Write-Host "Building and starting the updated PDP One services ..." -ForegroundColor Cyan
docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start after the update." }

$ready = $false
foreach ($attempt in 1..60) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8080" -TimeoutSec 8
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker compose logs --tail 80 nginx backend web
    throw "The updated application did not become ready in time. Review the log above."
}

Write-Host "" 
Write-Host "PDP One was updated successfully: http://localhost:8080" -ForegroundColor Green
Write-Host "Your existing secure settings and Docker data volumes were preserved." -ForegroundColor DarkGreen
