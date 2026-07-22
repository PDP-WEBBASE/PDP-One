#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1, 10)]
    [int]$Pages = 5
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDirectory = Join-Path $ProjectRoot ("PDP-ONE-PARSNAMAD-TENDER-REPAIR-" + $Timestamp)
$ReportJson = Join-Path $ReportDirectory "PDP-ONE-PARSNAMAD-TENDER-REPAIR-REPORT.json"
$CommandErrors = Join-Path $ReportDirectory "command-errors.txt"
$RuntimeLogs = Join-Path $ReportDirectory "runtime-logs.txt"
$SummaryPath = Join-Path $ReportDirectory "README-RESULTS.txt"
$LocalEnvPath = Join-Path $ProjectRoot ".env"
$CopiedTemporaryEnv = $false

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-EnvValue([string]$Path, [string]$Name) {
    $match = Select-String -LiteralPath $Path -Pattern "^$([regex]::Escape($Name))=(.*)$" |
        Select-Object -Last 1
    if ($null -eq $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim()
}

function Ensure-LocalEnvironmentFile {
    if (Test-Path -LiteralPath $LocalEnvPath) { return }

    $candidates = New-Object Collections.Generic.List[string]
    $installationPathFile = Join-Path $env:LOCALAPPDATA "PDP-One\installation-root.txt"
    if (Test-Path -LiteralPath $installationPathFile) {
        $installedRoot = [IO.File]::ReadAllText($installationPathFile).Trim()
        if ($installedRoot) {
            $candidates.Add((Join-Path $installedRoot ".env"))
        }
    }
    $candidates.Add("C:\PDP-One\.env")

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            Copy-Item -LiteralPath $candidate -Destination $LocalEnvPath -Force
            $script:CopiedTemporaryEnv = $true
            return
        }
    }
    throw "PDP One .env was not found in this package or the existing installation."
}

function New-PreRepairDatabaseBackup {
    $dbUser = Get-EnvValue -Path $LocalEnvPath -Name "POSTGRES_USER"
    $dbName = Get-EnvValue -Path $LocalEnvPath -Name "POSTGRES_DB"
    if ($dbUser -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $dbName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Database identifiers are not safe for the automatic backup command."
    }

    $preferredRoot = "D:\BackUp PDP-0NE-14050429-01"
    if (Test-Path -LiteralPath "D:\") {
        New-Item -ItemType Directory -Path $preferredRoot -Force | Out-Null
        $backupRoot = $preferredRoot
    } else {
        $backupRoot = Join-Path $ProjectRoot "backups"
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    }
    $backupPath = Join-Path $backupRoot ("PDP-ONE-PRE-PARSNAMAD-TENDER-REPAIR-" + $Timestamp + ".dump")
    $command = "docker compose exec -T db pg_dump --username $dbUser --dbname $dbName --format custom > `"$backupPath`""
    cmd /d /s /c $command
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath)) {
        throw "The pre-repair PostgreSQL backup failed. No cleanup was performed."
    }
    if ((Get-Item -LiteralPath $backupPath).Length -le 0) {
        throw "The pre-repair PostgreSQL backup is empty. No cleanup was performed."
    }
    return $backupPath
}

try {
    Write-Host "PDP One - Pars Namad tender repair and five-page retest" -ForegroundColor Green
    Write-Host "The incorrect controlled-test records will be cleaned safely." -ForegroundColor Cyan
    Write-Host "Selected or protected records are never deleted." -ForegroundColor DarkGreen

    if (-not (Test-Command "docker")) {
        throw "Docker is unavailable. Start Rancher Desktop and run this file again."
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        throw "The Docker engine is not ready. Start Rancher Desktop and wait until it is ready."
    }

    $requiredFiles = @(
        "backend\procurement\connectors\parsnamad.py",
        "backend\procurement\migrations\0012_fix_parsnamad_tender_route.py",
        "backend\procurement\management\commands\repair_and_retest_parsnamad_tenders.py"
    )
    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $requiredFile))) {
            throw "The repair package is incomplete. Missing: $requiredFile"
        }
    }

    Ensure-LocalEnvironmentFile
    New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null

    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    docker compose up --detach db redis
    if ($LASTEXITCODE -ne 0) { throw "PDP One data services could not be started." }

    $backupPath = New-PreRepairDatabaseBackup
    Write-Host "Pre-repair database backup created:" -ForegroundColor Green
    Write-Host $backupPath -ForegroundColor White

    Write-Host "Building the corrected backend image ..." -ForegroundColor Cyan
    docker compose build backend
    if ($LASTEXITCODE -ne 0) { throw "The corrected backend image could not be built." }

    Write-Host "Applying the corrected Pars Namad route migration ..." -ForegroundColor Cyan
    docker compose run --rm backend python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "The controlled migration failed." }

    Write-Host "Cleaning the incorrect test records and retesting five pages ..." -ForegroundColor Cyan
    $command = "docker compose run --rm backend python manage.py repair_and_retest_parsnamad_tenders --pages $Pages > `"$ReportJson`" 2> `"$CommandErrors`""
    cmd /d /s /c $command
    $testExitCode = $LASTEXITCODE

    docker compose logs --tail 150 db redis | Out-File -LiteralPath $RuntimeLogs -Encoding utf8

    $summary = @"
PDP ONE - PARS NAMAD TENDER REPAIR AND RETEST

Generated: $((Get-Date).ToString("o"))
Corrected route: https://www.parsnamaddata.com/tender/page-{page}
Page cap: $Pages
Details requested: false
ChatGPT analysis requested: false
Protected or selected notices deleted: false

Pre-repair database backup:
$backupPath

Report:
$ReportJson

The database backup is NOT included in the report ZIP.
"@
    [IO.File]::WriteAllText($SummaryPath, $summary, [Text.UTF8Encoding]::new($false))

    $zipPath = "$ReportDirectory.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $ReportDirectory "*") -DestinationPath $zipPath -CompressionLevel Optimal

    Write-Host ""
    Write-Host "Repair and retest report package:" -ForegroundColor Green
    Write-Host $zipPath -ForegroundColor White
    Write-Host "The separate backup remains at:" -ForegroundColor DarkGreen
    Write-Host $backupPath -ForegroundColor White

    if ($testExitCode -ne 0) {
        Write-Host "The retest reported a failure. Upload the report ZIP for analysis." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit $testExitCode
    }

    Write-Host "Pars Namad tender repair and retest completed successfully." -ForegroundColor Green
    Read-Host "Press Enter to close"
} finally {
    if ($CopiedTemporaryEnv -and (Test-Path -LiteralPath $LocalEnvPath)) {
        Remove-Item -LiteralPath $LocalEnvPath -Force -ErrorAction SilentlyContinue
    }
}
