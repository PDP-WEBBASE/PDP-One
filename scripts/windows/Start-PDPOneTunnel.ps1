#requires -Version 5.1
#requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Update-TunnelHosts {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) { return }

    $content = Get-Content -LiteralPath $envPath -Raw
    $updated = $content
    if ($updated -notmatch '(?m)^DJANGO_ALLOWED_HOSTS=.*\.pinggy-free\.link') {
        $updated = $updated -replace '(?m)^(DJANGO_ALLOWED_HOSTS=.*)$', '$1,.pinggy-free.link,.pinggy.link'
    }
    if ($updated -notmatch '(?m)^DJANGO_CSRF_TRUSTED_ORIGINS=.*\*\.pinggy-free\.link') {
        $updated = $updated -replace '(?m)^(DJANGO_CSRF_TRUSTED_ORIGINS=.*)$', '$1,https://*.pinggy-free.link,https://*.pinggy.link'
    }

    if ($updated -ne $content) {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($envPath, $updated, $utf8NoBom)
        Write-Host "Internet tunnel domains were added to the application allow-list." -ForegroundColor Green
    }
}

function Get-SshClient {
    $ssh = Get-Command "ssh.exe" -ErrorAction SilentlyContinue
    if ($ssh) { return $ssh.Source }

    $knownPath = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    if (Test-Path -LiteralPath $knownPath) { return $knownPath }

    Write-Host "Installing the Windows OpenSSH client for the fallback tunnel ..." -ForegroundColor Cyan
    Add-WindowsCapability -Online -Name "OpenSSH.Client~~~~0.0.1.0" -ErrorAction Stop | Out-Null
    if (Test-Path -LiteralPath $knownPath) { return $knownPath }
    throw "The Windows OpenSSH client could not be installed."
}

$localEnvPath = Join-Path $ProjectRoot ".env"
if (Test-Path -LiteralPath $localEnvPath) {
    Update-TunnelHosts
    docker compose up --detach
    if ($LASTEXITCODE -ne 0) { throw "PDP One failed to start." }
} else {
    Write-Host "No local configuration was found in this ZIP folder; using the already-running PDP One service." -ForegroundColor Yellow
    try {
        $localResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8080" -UseBasicParsing -TimeoutSec 10
        Write-Host "The installed PDP One service is available on port 8080." -ForegroundColor Green
    } catch {
        throw "PDP One is not available on http://127.0.0.1:8080. Run INSTALL-PDP-ONE.bat from the installed folder first."
    }
}

if (Get-Command "cloudflared" -ErrorAction SilentlyContinue) {
    Write-Host "Trying a temporary Cloudflare HTTPS URL ..." -ForegroundColor Yellow
    Write-Host "Keep this window open. Press Ctrl+C to stop the internet link." -ForegroundColor Cyan
    Write-Host ""
    cloudflared tunnel --url http://localhost:8080 --no-autoupdate
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Write-Host ""
    Write-Host "Cloudflare is unavailable on this network. Switching automatically to Pinggy over port 443 ..." -ForegroundColor Yellow
} else {
    Write-Host "Cloudflare is unavailable. Switching automatically to Pinggy over port 443 ..." -ForegroundColor Yellow
}

$sshPath = Get-SshClient
Write-Host ""
Write-Host "The HTTPS address printed below is the PDP One internet link." -ForegroundColor Green
Write-Host "The free fallback link lasts up to 60 minutes. Keep this window open." -ForegroundColor Cyan
Write-Host ""
& $sshPath -p 443 -t -o "StrictHostKeyChecking=accept-new" -o "ConnectTimeout=20" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" -o "ExitOnForwardFailure=yes" -R "0:127.0.0.1:8080" "free.pinggy.io" "u:Host:localhost" "u:Origin:https://localhost"
