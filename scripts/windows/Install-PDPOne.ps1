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
        throw "ابزار $CommandName نصب نیست. اسکریپت را بدون گزینه SkipPackageInstall اجرا کنید."
    }
    if (-not (Test-Command "winget")) {
        throw "Windows Package Manager (winget) در دسترس نیست. App Installer را از Microsoft Store نصب کنید."
    }
    Write-Host "در حال نصب $Id ..." -ForegroundColor Cyan
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "نصب $Id ناموفق بود." }
}

function New-RandomSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

Write-Host "PDP One - نصب خودکار نسخه آزمایشی ویندوز" -ForegroundColor Green
Install-WingetPackage "Git.Git" "git"
Install-WingetPackage "Docker.DockerDesktop" "docker"
Install-WingetPackage "Cloudflare.cloudflared" "cloudflared"

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (Test-Command "docker")) {
    $DockerCli = "C:\Program Files\Docker\Docker\resources\bin"
    if (Test-Path $DockerCli) { $env:Path = "$DockerCli;$env:Path" }
}

if (-not (Test-Command "docker")) {
    throw "Docker نصب شد اما هنوز در PATH فعال نیست. ویندوز را یک‌بار Restart و سپس همین اسکریپت را دوباره اجرا کنید."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $DockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $DockerDesktop) { Start-Process $DockerDesktop }
    Write-Host "در انتظار آماده‌شدن Docker Desktop ..." -ForegroundColor Yellow
    $ready = $false
    foreach ($attempt in 1..60) {
        Start-Sleep -Seconds 2
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) {
        throw "Docker Desktop آماده نشد. آن را باز کنید، راه‌اندازی اولیه WSL2 را کامل کنید و اسکریپت را دوباره اجرا کنید."
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
    Write-Host "فایل تنظیمات امن ایجاد شد." -ForegroundColor Green
} else {
    Write-Host "فایل .env موجود حفظ شد." -ForegroundColor DarkYellow
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "تنظیمات Docker Compose معتبر نیست." }

Write-Host "در حال دریافت و ساخت سرویس‌ها؛ این مرحله بار اول ممکن است چند دقیقه طول بکشد ..." -ForegroundColor Cyan
docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "راه‌اندازی سرویس‌های PDP One ناموفق بود." }

Write-Host "در انتظار آماده‌شدن برنامه ..." -ForegroundColor Yellow
$backendReady = $false
foreach ($attempt in 1..60) {
    docker compose exec -T backend python manage.py check *> $null
    if ($LASTEXITCODE -eq 0) { $backendReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $backendReady) {
    docker compose logs --tail 100 backend
    throw "بک‌اند PDP One در زمان مقرر آماده نشد. گزارش بالا را بررسی کنید."
}

if (-not $SkipAdministrator) {
    Write-Host "اکنون حساب مدیر اولیه را تعریف کنید." -ForegroundColor Yellow
    docker compose exec backend python manage.py createsuperuser
}

Write-Host "`nPDP One آماده است: http://localhost:8080" -ForegroundColor Green
Write-Host "برای لینک موقت اینترنتی اجرا کنید:" -ForegroundColor Cyan
Write-Host "powershell -ExecutionPolicy Bypass -File .\scripts\windows\Start-PDPOneTunnel.ps1"
