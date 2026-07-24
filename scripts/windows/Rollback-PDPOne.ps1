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

function Invoke-PDPOneDockerCompose {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$IgnoreFailure,
        [switch]$Quiet
    )

    $previousPreference = $ErrorActionPreference
    $nativeOutput = @()
    $exitCode = -1
    try {
        # Docker Compose emits normal lifecycle progress on stderr. Keep that
        # stream non-terminating under Windows PowerShell 5.1 and rely on the
        # native process exit code instead of NativeCommandError records.
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& docker compose @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if (-not $Quiet -and $nativeOutput.Count -gt 0) {
        $nativeText = ConvertTo-PDPOneRedactedText (($nativeOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if (-not [string]::IsNullOrWhiteSpace($nativeText)) { Write-Host $nativeText }
    }

    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (docker compose exit code $exitCode)."
    }
    return $exitCode
}

if (-not $Automatic) { throw "Rollback must be invoked by the authorized deployment workflow." }
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
Invoke-PDPOneDockerCompose -Arguments @("--profile", "tunnel", "stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale") -FailureMessage "Rollback service stop failed." -IgnoreFailure -Quiet | Out-Null
$temporary = Join-Path $env:TEMP ("pdp-one-code-rollback-" + [Guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -LiteralPath $CodeArchive -DestinationPath $temporary -Force
    & robocopy.exe $temporary $ProjectRoot /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XF .env /XD work backups .git node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Previous application files could not be restored." }
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
if ($RestoreDatabase) {
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Restore-PDPOneBackup.ps1") -BackupPath $BackupPath -AutomaticRollback -RestoreSettings -RestoreDatabase -RestorePrivateFiles -RestoreRedisData -RestoreTailscaleState
    if ($LASTEXITCODE -ne 0) { throw "Rollback backup restore failed." }
} else {
    Invoke-PDPOneDockerCompose -Arguments @("--profile", "tunnel", "up", "--detach", "--no-build") -FailureMessage "Rollback service startup failed." | Out-Null
}
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOne.ps1") -SkipChatGPTToolCheck
if ($LASTEXITCODE -ne 0) { throw "Rollback completed but health verification failed." }
Write-Host "Automatic rollback completed and the previous version is healthy." -ForegroundColor Green
