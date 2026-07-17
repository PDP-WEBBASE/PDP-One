#requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

docker compose stop
if ($LASTEXITCODE -ne 0) { throw "PDP One failed to stop." }
Write-Host "PDP One stopped. Stored data was not deleted." -ForegroundColor Green
