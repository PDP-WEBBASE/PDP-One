[CmdletBinding()]
param(
    [switch]$SkipPackageInstall,
    [switch]$SkipAdministrator
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$CommandName) {
    if (Test-Command $CommandName) { return }
    if ($SkipPackageInstall) {
        throw "$CommandName is not installed. Run this script without SkipPackageInstall."
    }
    if (-not (Test-Command "winget")) {
        throw "Windows Package Manager (winget) is unavailable. Install App Installer from Microsoft Store."
    }
    Write-Host "Installing $Id ..." -ForegroundColor Cyan
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Installation failed for $Id." }
}

function New-RandomSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

Write-Host "PDP One - Windows trial installer" -ForegroundColor Green
Install-WingetPackage "Git.Git" "git"
Install-WingetPackage "Docker.DockerDesktop" "docker"
Install-WingetPackage "Cloudflare.cloudflared" "cloudflared"

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (Test-Command "docker")) {
    $DockerCli = "C:\Program Files\Docker\Docker\resources\bin"
    if (Test-Path $DockerCli) { $env:Path = "$DockerCli;$env:Path" }
}

if (-not (Test-Command "docker")) {
    throw "Docker was installed but is not active in PATH. Restart Windows, then run this installer again."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $DockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $DockerDesktop) { Start-Process $DockerDesktop }
    Write-Host "Waiting for Docker Desktop ..." -ForegroundColor Yellow
    $ready = $false
    foreach ($attempt in 1..60) {
        Start-Sleep -Seconds 2
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) {
        throw "Docker Desktop did not become ready. Open it, finish initial WSL2 setup, and run this installer again."
    }
}

$EnvPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvPath)) {
    $postgresPassword = New-RandomSecret 30
    $djangoSecret = New-RandomSecret 48
    $mcpToken = New-RandomSecret 48
    $content = Get-Content (Join-Path $ProjectRoot ".env.example") -Raw
    $content = $content.Replace("POSTGRES_PASSWORD=change-me", "POSTGRES_PASSWORD=$postgresPassword")
    $content = $content.Replace("postgresql://pdp_one:change-me@db:5432/pdp_one", "postgresql://pdp_one:$postgresPassword@db:5432/pdp_one")
    $content = $content.Replace("DJANGO_SECRET_KEY=change-this-in-production", "DJANGO_SECRET_KEY=$djangoSecret")
    $content = $content.Replace("PDP_MCP_TOKEN=replace-with-a-long-random-token", "PDP_MCP_TOKEN=$mcpToken")
    [IO.File]::WriteAllText($EnvPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Host "Secure configuration file created." -ForegroundColor Green
} else {
    Write-Host "Existing .env file preserved." -ForegroundColor DarkYellow
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

Write-Host "Downloading and building services. The first run may take several minutes ..." -ForegroundColor Cyan
docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start." }

Write-Host "Waiting for the application ..." -ForegroundColor Yellow
$backendReady = $false
foreach ($attempt in 1..60) {
    docker compose exec -T backend python manage.py check *> $null
    if ($LASTEXITCODE -eq 0) { $backendReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $backendReady) {
    docker compose logs --tail 100 backend
    throw "PDP One backend did not become ready in time. Review the log above."
}

if (-not $SkipAdministrator) {
    Write-Host "Create the initial administrator account now." -ForegroundColor Yellow
    docker compose exec backend python manage.py createsuperuser
}

Write-Host "`nPDP One is ready: http://localhost:8080" -ForegroundColor Green
Write-Host "To create a temporary internet link, run:" -ForegroundColor Cyan
Write-Host "powershell -ExecutionPolicy Bypass -File .\scripts\windows\Start-PDPOneTunnel.ps1"
