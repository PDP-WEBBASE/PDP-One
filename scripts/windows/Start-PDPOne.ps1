$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
docker compose up --detach
if ($LASTEXITCODE -ne 0) { throw "راه‌اندازی PDP One ناموفق بود." }
Write-Host "PDP One فعال است: http://localhost:8080" -ForegroundColor Green
