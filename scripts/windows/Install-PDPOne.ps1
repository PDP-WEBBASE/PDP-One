#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [switch]$SkipPackageInstall,
    [switch]$SkipAdministrator
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$InstallerVersion = "2026.07.18.14"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
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
    winget install --id $Id --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Installation failed for $Id. Exit code: $LASTEXITCODE" }
    Refresh-Path
}

function New-RandomSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Add-RancherPaths {
    $candidates = @(
        "C:\Program Files\Rancher Desktop\resources\resources\win32\bin",
        (Join-Path $env:LOCALAPPDATA "Programs\Rancher Desktop\resources\resources\win32\bin")
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate) -and ($env:Path -notlike "*$candidate*")) {
            $env:Path = "$candidate;$env:Path"
        }
    }
}

function Start-RancherDesktop {
    $executables = @(
        "C:\Program Files\Rancher Desktop\Rancher Desktop.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Rancher Desktop\Rancher Desktop.exe")
    )
    foreach ($executable in $executables) {
        if (Test-Path $executable) {
            Start-Process -FilePath $executable
            return
        }
    }
    throw "Rancher Desktop was installed but its executable could not be found."
}

function Install-DockerRegistryMirror {
    $provisioningDirectory = Join-Path $env:LOCALAPPDATA "rancher-desktop\provisioning"
    $provisioningPath = Join-Path $provisioningDirectory "pdp-one-registry-mirror.start"
    $scriptContent = @'
#!/bin/sh
set -e
mkdir -p /etc/conf.d /etc/docker
touch /etc/conf.d/docker
sed -i '/PDP_ONE_REGISTRY_MIRROR/d' /etc/conf.d/docker
cat <<'PDPONEOPTS' >> /etc/conf.d/docker
DOCKER_OPTS="${DOCKER_OPTS} --registry-mirror=https://mirror.gcr.io" # PDP_ONE_REGISTRY_MIRROR
PDPONEOPTS
if [ ! -s /etc/docker/daemon.json ]; then
  cat <<'PDPONEJSON' > /etc/docker/daemon.json
{
  "registry-mirrors": ["https://mirror.gcr.io"]
}
PDPONEJSON
fi
'@
    $scriptContent = $scriptContent -replace "`r`n", "`n"

    New-Item -ItemType Directory -Path $provisioningDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $provisioningPath) {
        $existing = [IO.File]::ReadAllText($provisioningPath)
        if ($existing -eq $scriptContent) { return $false }
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($provisioningPath, $scriptContent, $utf8NoBom)
    Write-Host "The free Google Docker Hub cache has been configured for Rancher Desktop." -ForegroundColor Green
    return $true
}

function Restart-RancherForProvisioning {
    Write-Host "Restarting Rancher Desktop to activate the registry mirror ..." -ForegroundColor Yellow
    if (Test-Command "rdctl") {
        rdctl shutdown
        Start-Sleep -Seconds 5
    }
    Start-RancherDesktop

    foreach ($attempt in 1..180) {
        Start-Sleep -Seconds 2
        Add-RancherPaths
        cmd /c "docker info >nul 2>&1"
        if ($LASTEXITCODE -eq 0) { return }
        if (($attempt % 15) -eq 0) {
            Write-Host "Rancher Desktop is applying the registry mirror; please wait ..." -ForegroundColor DarkYellow
        }
    }
    throw "Rancher Desktop did not restart after registry mirror configuration."
}

function Enable-RequiredWindowsFeatures {
    $requiredFeatures = @(
        "Microsoft-Windows-Subsystem-Linux",
        "VirtualMachinePlatform"
    )
    $restartRequired = $false

    foreach ($featureName in $requiredFeatures) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName -ErrorAction Stop
        if ($feature.State -eq "Enabled") {
            Write-Host "$featureName is enabled." -ForegroundColor DarkGreen
            continue
        }
        if ($feature.State -eq "EnablePending") {
            Write-Host "$featureName is waiting for a Windows restart." -ForegroundColor Yellow
            $restartRequired = $true
            continue
        }

        Write-Host "Enabling required Windows feature: $featureName ..." -ForegroundColor Cyan
        Enable-WindowsOptionalFeature -Online -FeatureName $featureName -All -NoRestart -ErrorAction Stop | Out-Null
        $restartRequired = $true
    }

    if ($restartRequired) {
        Write-Host ""
        Write-Host "The required WSL features are now enabled, but Windows must restart before installation can continue." -ForegroundColor Yellow
        $answer = Read-Host "Restart Windows automatically in 30 seconds? Enter Y for yes"
        if ($answer -match "^(?i:y|yes)$") {
            shutdown.exe /r /t 30 /c "PDP One enabled the required WSL features. Windows must restart."
            Write-Host "Windows restart scheduled. Save any open work now. To cancel, run: shutdown /a" -ForegroundColor Yellow
        } else {
            Write-Host "Please restart Windows manually, then run INSTALL-PDP-ONE.bat again." -ForegroundColor Yellow
        }
        exit 0
    }
}

Write-Host "PDP One Windows installer $InstallerVersion" -ForegroundColor Green
Enable-RequiredWindowsFeatures
Install-WingetPackage "Git.Git" "git"
Install-WingetPackage "Cloudflare.cloudflared" "cloudflared"

$engineReady = $false
if (Test-Command "docker") {
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { $engineReady = $true }
}

if (-not $engineReady) {
    Write-Host "Installing Rancher Desktop as the Docker-compatible container engine ..." -ForegroundColor Cyan
    Install-WingetPackage "SUSE.RancherDesktop" "rdctl"
    Refresh-Path
    Add-RancherPaths
    if (Test-Command "rdctl") {
        Write-Host "Starting Rancher Desktop with Moby and without Kubernetes ..." -ForegroundColor Cyan
        rdctl start --container-engine.name=moby --kubernetes.enabled=false
        if ($LASTEXITCODE -ne 0) {
            Write-Host "rdctl start did not complete; opening Rancher Desktop for initial setup ..." -ForegroundColor Yellow
            Start-RancherDesktop
        }
    } else {
        Start-RancherDesktop
    }

    Write-Host "Waiting for Rancher Desktop and the Moby engine ..." -ForegroundColor Yellow
    foreach ($attempt in 1..300) {
        Start-Sleep -Seconds 2
        Add-RancherPaths
        if (Test-Command "docker") {
            cmd /c "docker info >nul 2>&1"
            if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
        }
        if (($attempt % 15) -eq 0) {
            Write-Host "Rancher Desktop is still starting; please wait ..." -ForegroundColor DarkYellow
        }
    }
}

if (-not $engineReady) {
    Write-Host "The container engine is not ready. Automatic diagnostics will run now ..." -ForegroundColor Red
    $diagnosticScript = Join-Path $PSScriptRoot "Diagnose-PDPOne.ps1"
    if (Test-Path -LiteralPath $diagnosticScript) {
        & $diagnosticScript
        Write-Host "Diagnostics were saved to pdp-one-diagnostics.txt." -ForegroundColor Yellow
    } else {
        Write-Host "The diagnostics script is missing. Download the latest repository ZIP." -ForegroundColor Yellow
    }
    exit 1
}

cmd /c "docker compose version >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is unavailable. In Rancher Desktop select the Moby container engine, then run this installer again."
}

if (Install-DockerRegistryMirror) {
    Restart-RancherForProvisioning
}

$containerRegistry = "docker.arvancloud.ir/library"
Write-Host "Downloading required container images from the direct regional mirror ..." -ForegroundColor Cyan
$requiredImages = @(
    "$containerRegistry/postgres:17-alpine",
    "$containerRegistry/redis:7-alpine",
    "$containerRegistry/nginx:1.27-alpine",
    "$containerRegistry/python:3.13-slim",
    "$containerRegistry/node:22-bookworm-slim"
)
foreach ($image in $requiredImages) {
    cmd /c "docker image inspect $image >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { continue }
    Write-Host "Downloading $image ..." -ForegroundColor Cyan
    docker pull $image
    if ($LASTEXITCODE -ne 0) {
        throw "Could not download $image from the direct regional mirror."
    }
}

$EnvPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvPath)) {
    $postgresPassword = New-RandomSecret 30
    $djangoSecret = New-RandomSecret 48
    $mcpToken = New-RandomSecret 48
    $envTemplatePath = Join-Path $ProjectRoot ".env.example"
    if (Test-Path -LiteralPath $envTemplatePath) {
        $envContent = Get-Content -LiteralPath $envTemplatePath -Raw
    } else {
        Write-Host ".env.example is missing; using the built-in safe template." -ForegroundColor Yellow
        $envContent = @"
PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
POSTGRES_DB=pdp_one
POSTGRES_USER=pdp_one
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=postgresql://pdp_one:change-me@db:5432/pdp_one
DJANGO_SECRET_KEY=change-this-in-production
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend,nginx,.trycloudflare.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com
REDIS_URL=redis://redis:6379/0
PDP_API_URL=http://backend:8000/api/v1
PDP_MCP_TOKEN=replace-with-a-long-random-token
"@
    }
    $envContent = $envContent.Replace("POSTGRES_PASSWORD=change-me", "POSTGRES_PASSWORD=$postgresPassword")
    $envContent = $envContent.Replace("postgresql://pdp_one:change-me@db:5432/pdp_one", "postgresql://pdp_one:$postgresPassword@db:5432/pdp_one")
    $envContent = $envContent.Replace("DJANGO_SECRET_KEY=change-this-in-production", "DJANGO_SECRET_KEY=$djangoSecret")
    $envContent = $envContent.Replace("PDP_MCP_TOKEN=replace-with-a-long-random-token", "PDP_MCP_TOKEN=$mcpToken")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($EnvPath, $envContent, $utf8NoBom)
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
    cmd /c "docker compose exec -T backend python manage.py check >nul 2>&1"
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

Write-Host ""
Write-Host "PDP One is ready: http://localhost:8080" -ForegroundColor Green
Write-Host "To create a temporary internet link, double-click START-INTERNET-LINK.bat" -ForegroundColor Cyan
