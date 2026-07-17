#requires -Version 5.1
#requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared is not installed. Run INSTALL-PDP-ONE.bat first."
}

docker compose up --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One failed to start." }

Write-Host "A temporary HTTPS URL will be created." -ForegroundColor Yellow
Write-Host "Keep this window open. Press Ctrl+C to stop the internet link." -ForegroundColor Cyan
Write-Host ""
cloudflared tunnel --url http://localhost:8080 --no-autoupdate
