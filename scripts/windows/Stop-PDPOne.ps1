$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
docker compose stop
if ($LASTEXITCODE -ne 0) { throw "توقف PDP One ناموفق بود." }
Write-Host "سرویس‌های PDP One متوقف شدند. داده‌ها حذف نشده‌اند." -ForegroundColor Green
