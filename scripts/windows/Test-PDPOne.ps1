$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose نامعتبر است." }

$running = docker compose ps --status running --services
$required = @("db", "redis", "backend", "worker", "beat", "mcp", "web", "nginx")
$missing = $required | Where-Object { $_ -notin $running }
if ($missing.Count -gt 0) { throw "سرویس‌های غیرفعال: $($missing -join ', ')" }

$response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 20
if ($response.StatusCode -ne 200) { throw "وب‌سایت پاسخ سالم نداد." }
Write-Host "تمام سرویس‌ها و وب‌سایت PDP One سالم هستند." -ForegroundColor Green
