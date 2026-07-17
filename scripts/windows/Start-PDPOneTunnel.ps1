$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared نصب نیست. ابتدا Install-PDPOne.ps1 را اجرا کنید."
}

docker compose up --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One اجرا نشد." }

Write-Host "یک لینک HTTPS موقت ساخته می‌شود. تا زمان بازبودن این پنجره، لینک فعال می‌ماند." -ForegroundColor Yellow
Write-Host "برای توقف لینک، Ctrl+C را فشار دهید.`n" -ForegroundColor Cyan
cloudflared tunnel --url http://localhost:8080 --no-autoupdate
