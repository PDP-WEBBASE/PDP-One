#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param([switch]$Confirmed, [switch]$NonInteractive)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot

if (-not $Confirmed) {
    Write-Host "Rotation temporarily disconnects the existing ChatGPT app and requires a one-time MCP URL update." -ForegroundColor Yellow
    if ($NonInteractive -or (Read-Host "Type ROTATE to continue") -cne "ROTATE") { throw "Token rotation was not confirmed." }
}

$backupDir = Join-Path $ProjectRoot "work\secure-settings-backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupPath = Join-Path $backupDir ("env-before-token-rotation-{0}.dpapi" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
Protect-PDPOneSecretFile -InputPath $envPath -OutputPath $backupPath
$oldToken = Get-PDPOneEnvValue $envPath "PDP_MCP_PATH_TOKEN"
$newToken = New-PDPOneSecret 32
try {
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN" -Value $newToken
    & docker compose up --detach --no-deps --force-recreate nginx
    if ($LASTEXITCODE -ne 0 -or -not (Wait-PDPOneUrl "http://127.0.0.1:8080/healthz" 90)) { throw "Health check failed after rotation." }
    $null = Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot -AcceptCurrent
    Write-Host "MCP path token rotated successfully. The old path is inactive." -ForegroundColor Green
    Write-Host "Run CONNECT-CHATGPT.bat once to refresh the private connection instructions." -ForegroundColor Cyan
} catch {
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN" -Value $oldToken
    & docker compose up --detach --no-deps --force-recreate nginx *> $null
    $null = Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot -AcceptCurrent
    throw "Rotation failed and the previous token was restored: $($_.Exception.Message)"
}
