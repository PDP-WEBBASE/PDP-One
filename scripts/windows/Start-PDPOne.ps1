#requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

docker compose up --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One failed to start." }
Write-Host "PDP One is running: http://localhost:8080" -ForegroundColor Green
