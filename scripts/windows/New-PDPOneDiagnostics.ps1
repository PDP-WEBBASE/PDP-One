#requires -Version 5.1
[CmdletBinding()]
param([string]$FailureMessage = "Unspecified failure", [string]$DeploymentId = "", [string]$BackupId = "", [string]$RollbackResult = "not-run")

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
$reportDir = Join-Path $ProjectRoot "work\diagnostics"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$path = Join-Path $reportDir ("PDP-ONE-DIAGNOSTICS-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$lines = @(
    "PDP One secure diagnostics",
    "Generated: $((Get-Date).ToUniversalTime().ToString('o'))",
    "Failure: $FailureMessage",
    "Deployment ID: $DeploymentId",
    "Backup ID: $BackupId",
    "Rollback: $RollbackResult",
    "Windows: $([Environment]::OSVersion.VersionString)",
    "Docker: $(& docker version --format '{{.Server.Version}}' 2>$null)",
    "Compose: $(& docker compose version 2>$null)",
    "",
    "Compose status:",
    ($(& docker compose --profile tunnel ps 2>&1 | Out-String)),
    "",
    "Redacted service logs:",
    ($(& docker compose --profile tunnel logs --tail 80 nginx backend mcp worker beat tailscale 2>&1 | Out-String))
) -join [Environment]::NewLine
$safe = ConvertTo-PDPOneRedactedText -Text $lines
[IO.File]::WriteAllText($path, $safe, [Text.UTF8Encoding]::new($false))
Write-Host "Secure diagnostics written to $path" -ForegroundColor Yellow
