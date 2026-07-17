#requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

$running = docker compose ps --status running --services
$required = @("db", "redis", "backend", "worker", "beat", "mcp", "web", "nginx")
$missing = $required | Where-Object { $_ -notin $running }
if ($missing.Count -gt 0) { throw "Inactive services: $($missing -join ', ')" }

$response = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 20
if ($response.StatusCode -ne 200) { throw "The web application did not return HTTP 200." }
Write-Host "All PDP One services are healthy." -ForegroundColor Green
