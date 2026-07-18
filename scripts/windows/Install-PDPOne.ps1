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

$InstallerVersion = "2026.07.19.19"
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

function Get-EnvValue([string]$Path, [string]$Name) {
    $match = Select-String -LiteralPath $Path -Pattern "^$([regex]::Escape($Name))=(.*)$" |
        Select-Object -Last 1
    if ($null -eq $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim()
}

function Find-PdpPostgresVolume {
    $volumeName = (& docker volume ls --filter "label=com.docker.compose.project=pdp-one" --filter "label=com.docker.compose.volume=postgres_data" --format "{{.Name}}" 2>$null |
        Select-Object -First 1)

    if (-not [string]::IsNullOrWhiteSpace($volumeName)) {
        return ([string]$volumeName).Trim()
    }

    cmd /c "docker volume inspect pdp-one_postgres_data >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { return "pdp-one_postgres_data" }
    return $null
}

function Test-PostgresDataVolume {
    param(
        [string]$VolumeName,
        [string]$ImageName
    )
    if ([string]::IsNullOrWhiteSpace($VolumeName)) { return $false }

    $arguments = @(
        "run",
        "--rm",
        "--volume",
        "${VolumeName}:/var/lib/postgresql/data:ro",
        "--entrypoint",
        "sh",
        $ImageName,
        "-c",
        "test -s /var/lib/postgresql/data/PG_VERSION"
    )

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker @arguments *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Repair-PostgresCredential {
    param(
        [string]$PostgresUser,
        [string]$PostgresDb,
        [string]$PostgresPassword
    )
    if ($PostgresUser -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "The PostgreSQL user name is not safe for automatic recovery."
    }
    if ($PostgresDb -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "The PostgreSQL database name is not safe for automatic recovery."
    }
    if ($PostgresPassword -notmatch '^[A-Za-z0-9_-]{20,}$') {
        throw "The PostgreSQL password format is not safe for automatic recovery."
    }

    Write-Host "Existing PDP One PostgreSQL data was detected." -ForegroundColor Yellow
    Write-Host "Synchronizing its database credential without deleting the data volume ..." -ForegroundColor Cyan

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker compose up --detach db 2>&1 | Out-Host
        $startCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($startCode -ne 0) {
        throw "The existing PostgreSQL service could not be started for recovery."
    }

    $databaseReady = $false
    foreach ($attempt in 1..60) {
        cmd /c "docker compose exec -T db pg_isready -U $PostgresUser -d $PostgresDb >nul 2>&1"
        if ($LASTEXITCODE -eq 0) {
            $databaseReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $databaseReady) {
        throw "The existing PostgreSQL data did not become ready for recovery."
    }

    $sql = "ALTER ROLE `"$PostgresUser`" WITH PASSWORD '$PostgresPassword';"
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker compose exec -T --user postgres db psql --username $PostgresUser --dbname $PostgresDb --set "ON_ERROR_STOP=1" --command $sql 2>&1 | Out-Host
        $repairCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($repairCode -ne 0) {
        throw "The existing PostgreSQL password could not be synchronized. The data volume was not deleted."
    }

    Write-Host "Existing PostgreSQL data was recovered successfully." -ForegroundColor Green
}

function Get-FreeSystemDriveBytes {
    $driveName = $env:SystemDrive.TrimEnd(':')
    return (Get-PSDrive -Name $driveName).Free
}

function Invoke-SafeDockerCacheCleanup([string]$Reason) {
    Write-Host $Reason -ForegroundColor Cyan
    Write-Host "Persistent database, Redis and private-file volumes are protected." -ForegroundColor DarkGreen

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker builder prune --all --force 2>&1 | Out-Host
        & docker image prune --force 2>&1 | Out-Host
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Protect-LowDiskBeforeBuild {
    $freeBytes = Get-FreeSystemDriveBytes
    Write-Host ("Free system-drive space before build: {0:N2} GB" -f ($freeBytes / 1GB)) -ForegroundColor Cyan
    if ($freeBytes -lt 12GB) {
        Invoke-SafeDockerCacheCleanup -Reason "Low disk space detected. Removing unused build cache before the build ..."
    }
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
    $mcpPathToken = New-RandomSecret 32
    $trialAdminPassword = New-RandomSecret 24
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
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend,nginx,.trycloudflare.com,.pinggy-free.link,.pinggy.link
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com,https://*.pinggy-free.link,https://*.pinggy.link
REDIS_URL=redis://redis:6379/0
PDP_API_URL=http://backend:8000/api/v1
PDP_MCP_TOKEN=replace-with-a-long-random-token
PDP_MCP_PATH_TOKEN=replace-with-a-random-path-token
PDP_TRIAL_MODE=true
PDP_TRIAL_ADMIN_USERNAME=pdp-admin
PDP_TRIAL_ADMIN_PASSWORD=replace-with-a-random-password
"@
    }
    $envContent = $envContent.Replace("POSTGRES_PASSWORD=change-me", "POSTGRES_PASSWORD=$postgresPassword")
    $envContent = $envContent.Replace("postgresql://pdp_one:change-me@db:5432/pdp_one", "postgresql://pdp_one:$postgresPassword@db:5432/pdp_one")
    $envContent = $envContent.Replace("DJANGO_SECRET_KEY=change-this-in-production", "DJANGO_SECRET_KEY=$djangoSecret")
    $envContent = $envContent.Replace("PDP_MCP_TOKEN=replace-with-a-long-random-token", "PDP_MCP_TOKEN=$mcpToken")
    $envContent = $envContent.Replace("PDP_MCP_PATH_TOKEN=replace-with-a-random-path-token", "PDP_MCP_PATH_TOKEN=$mcpPathToken")
    $envContent = $envContent.Replace("PDP_TRIAL_ADMIN_PASSWORD=replace-with-a-random-password", "PDP_TRIAL_ADMIN_PASSWORD=$trialAdminPassword")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($EnvPath, $envContent, $utf8NoBom)
    Write-Host "Secure configuration file created." -ForegroundColor Green
} else {
    Write-Host "Existing .env file preserved." -ForegroundColor DarkYellow
    $envContent = [IO.File]::ReadAllText($EnvPath)
    if ($envContent -notmatch '(?m)^PDP_MCP_PATH_TOKEN=') {
        $envContent = $envContent.TrimEnd() + "`r`nPDP_MCP_PATH_TOKEN=$(New-RandomSecret 32)`r`n"
    }
    if ($envContent -notmatch '(?m)^PDP_TRIAL_MODE=') {
        $envContent = $envContent.TrimEnd() + "`r`nPDP_TRIAL_MODE=true`r`n"
    }
    if ($envContent -notmatch '(?m)^PDP_TRIAL_ADMIN_USERNAME=') {
        $envContent = $envContent.TrimEnd() + "`r`nPDP_TRIAL_ADMIN_USERNAME=pdp-admin`r`n"
    }
    if ($envContent -notmatch '(?m)^PDP_TRIAL_ADMIN_PASSWORD=') {
        $envContent = $envContent.TrimEnd() + "`r`nPDP_TRIAL_ADMIN_PASSWORD=$(New-RandomSecret 24)`r`n"
    }
    [IO.File]::WriteAllText($EnvPath, $envContent, [Text.UTF8Encoding]::new($false))
}

$postgresImage = "$containerRegistry/postgres:17-alpine"
$postgresVolumeName = Find-PdpPostgresVolume
if (Test-PostgresDataVolume -VolumeName $postgresVolumeName -ImageName $postgresImage) {
    $postgresUser = Get-EnvValue -Path $EnvPath -Name "POSTGRES_USER"
    $postgresDb = Get-EnvValue -Path $EnvPath -Name "POSTGRES_DB"
    $postgresPassword = Get-EnvValue -Path $EnvPath -Name "POSTGRES_PASSWORD"
    Repair-PostgresCredential -PostgresUser $postgresUser -PostgresDb $postgresDb -PostgresPassword $postgresPassword
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

Protect-LowDiskBeforeBuild
Write-Host "Downloading and building services. The first run may take several minutes ..." -ForegroundColor Cyan
docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start." }
Invoke-SafeDockerCacheCleanup -Reason "Build completed. Removing build cache that is no longer needed at runtime ..."

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

$adminSyncScript = @(
    'import os',
    'from django.contrib.auth import get_user_model',
    'User = get_user_model()',
    'username = os.environ["PDP_TRIAL_ADMIN_USERNAME"]',
    'password = os.environ["PDP_TRIAL_ADMIN_PASSWORD"]',
    'user, _ = User.objects.get_or_create(username=username)',
    'user.set_password(password)',
    'user.is_active = True',
    'user.is_staff = True',
    'user.is_superuser = True',
    'user.save()'
) -join "`n"
$previousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $adminSyncOutput = ($adminSyncScript | & docker compose exec -T backend python manage.py shell 2>&1)
    $adminSyncCode = $LASTEXITCODE
    $adminSyncOutput | Out-Host
} finally {
    $ErrorActionPreference = $previousErrorAction
}
if ($adminSyncCode -ne 0) {
    throw "The trial administrator account could not be synchronized."
}

$adminUser = ((Select-String -LiteralPath $EnvPath -Pattern '^PDP_TRIAL_ADMIN_USERNAME=(.*)$').Matches.Groups[1].Value)
$adminPassword = ((Select-String -LiteralPath $EnvPath -Pattern '^PDP_TRIAL_ADMIN_PASSWORD=(.*)$').Matches.Groups[1].Value)
$loginPath = Join-Path $ProjectRoot "PDP-ONE-LOCAL-LOGIN.txt"
$loginText = "PDP One local address: http://localhost:8080`r`nUsername: $adminUser`r`nPassword: $adminPassword`r`n`r`nKeep this file private."
[IO.File]::WriteAllText($loginPath, $loginText, [Text.UTF8Encoding]::new($false))

$stateDirectory = Join-Path $env:LOCALAPPDATA "PDP-One"
$installationPathFile = Join-Path $stateDirectory "installation-root.txt"
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
[IO.File]::WriteAllText($installationPathFile, $ProjectRoot, [Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "PDP One is ready: http://localhost:8080" -ForegroundColor Green
Write-Host "Opening the automatic ChatGPT connection now. No OpenAI API key is used." -ForegroundColor Cyan
Start-Process notepad.exe -ArgumentList $loginPath
Start-Process -FilePath (Join-Path $ProjectRoot "CONNECT-CHATGPT.bat") -WorkingDirectory $ProjectRoot
