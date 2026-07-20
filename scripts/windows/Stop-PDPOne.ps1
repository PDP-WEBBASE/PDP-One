#requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
& docker compose --profile tunnel stop
if ($LASTEXITCODE -ne 0) { throw "PDP One could not be stopped cleanly." }
Write-Host "PDP One stopped. Data volumes, Tailscale identity, Funnel configuration, and MCP tokens were preserved." -ForegroundColor Green
