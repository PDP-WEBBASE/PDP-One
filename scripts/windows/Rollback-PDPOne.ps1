#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][string]$CodeArchive,
    [switch]$Automatic,
    [switch]$RestoreDatabase
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
if (-not $Automatic) { throw "Rollback must be invoked by the authorized deployment workflow." }
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
& docker compose --profile tunnel stop backend worker beat mcp web nginx tailscale *> $null
$temporary = Join-Path $env:TEMP ("pdp-one-code-rollback-" + [Guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -LiteralPath $CodeArchive -DestinationPath $temporary -Force
    & robocopy.exe $temporary $ProjectRoot /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD work backups .git node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Previous application files could not be restored." }
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
if ($RestoreDatabase) {
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Restore-PDPOneBackup.ps1") -BackupPath $BackupPath -AutomaticRollback -RestoreSettings -RestoreDatabase -RestorePrivateFiles -RestoreRedisData -RestoreTailscaleState
} else {
    & docker compose --profile tunnel up --detach --no-build
}
if ($LASTEXITCODE -ne 0) { throw "Rollback service startup failed." }
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOne.ps1") -SkipChatGPTToolCheck
if ($LASTEXITCODE -ne 0) { throw "Rollback completed but health verification failed." }
Write-Host "Automatic rollback completed and the previous version is healthy." -ForegroundColor Green
