#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$Pages = 2
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDirectory = Join-Path $ProjectRoot ("PDP-ONE-SETAD-LIVE-TEST-" + $Timestamp)
$ReportJson = Join-Path $ReportDirectory "PDP-ONE-SETAD-LIVE-TEST-REPORT.json"
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
            Write-Host "Using the existing local PDP One configuration for this test." -ForegroundColor DarkGreen
            return
        }
    }
    throw "PDP One .env was not found in this package or the existing installation."
}

function New-PreTestDatabaseBackup {
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
    $backupPath = Join-Path $backupRoot ("PDP-ONE-PRE-SETAD-TEST-" + $Timestamp + ".dump")
    $command = "docker compose exec -T db pg_dump --username $dbUser --dbname $dbName --format custom > `"$backupPath`""
    cmd /d /s /c $command
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath)) {
        throw "The pre-test PostgreSQL backup failed. The test was not started."
    }
    if ((Get-Item -LiteralPath $backupPath).Length -le 0) {
        throw "The pre-test PostgreSQL backup is empty. The test was not started."
    }
    return $backupPath
}

try {
    Write-Host "PDP One - SETAD controlled live test" -ForegroundColor Green
    Write-Host "Page cap per connector: $Pages" -ForegroundColor Cyan
    Write-Host "Public lists only; details and analysis are disabled." -ForegroundColor DarkGreen
    Write-Host "The currently running PDP One backend will not be replaced." -ForegroundColor DarkGreen

    if (-not (Test-Command "docker")) {
        throw "Docker is unavailable. Start Rancher Desktop and run this file again."
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        throw "The Docker engine is not ready. Start Rancher Desktop and wait until it is ready."
    }
    cmd /c "docker compose version >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is unavailable."
    }

    $requiredFiles = @(
        "backend\procurement\connectors\setad.py",
        "backend\procurement\connectors\fetchers.py",
        "backend\procurement\migrations\0011_configure_setad_public_connectors.py",
        "backend\procurement\management\commands\test_setad_connectors.py"
    )
    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $requiredFile))) {
            throw "The local PDP One code is not the approved SETAD test version. Missing: $requiredFile"
        }
    }

    Ensure-LocalEnvironmentFile
    New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null

    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

    docker compose up --detach db redis
    if ($LASTEXITCODE -ne 0) { throw "PDP One data services could not be started." }

    $backupPath = New-PreTestDatabaseBackup
    Write-Host "Pre-test database backup created:" -ForegroundColor Green
    Write-Host $backupPath -ForegroundColor White

    Write-Host "Building the approved test backend image ..." -ForegroundColor Cyan
    docker compose build backend
    if ($LASTEXITCODE -ne 0) { throw "The backend test image could not be built." }

    Write-Host "Applying controlled migrations in an ephemeral container ..." -ForegroundColor Cyan
    docker compose run --rm backend python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "The controlled migration failed." }

    Write-Host "Running SETAD tenders and inquiries tests in an ephemeral container ..." -ForegroundColor Cyan
    $testCommand = "docker compose run --rm backend python manage.py test_setad_connectors --pages $Pages --connector all > `"$ReportJson`" 2> `"$CommandErrors`""
    cmd /d /s /c $testCommand
    $testExitCode = $LASTEXITCODE

    $logsCommand = "docker compose logs --tail 150 db redis > `"$RuntimeLogs`" 2>&1"
    cmd /d /s /c $logsCommand

    $summary = @"
PDP ONE - SETAD CONTROLLED LIVE TEST

Generated: $((Get-Date).ToString("o"))
Page cap per connector: $Pages
Details requested: false
ChatGPT analysis requested: false
SETAD source activated: true
Connectors activated: setad_tenders, setad_inquiries
Active backend replaced: false
Test execution: ephemeral backend container
Report encoding: raw UTF-8

Pre-test database backup:
$backupPath

Report:
$ReportJson

The database backup is NOT included in the report ZIP.
No login, captcha bypass, stored browser cookie or permanent SETAD token was used.
"@
    [IO.File]::WriteAllText($SummaryPath, $summary, [Text.UTF8Encoding]::new($false))

    $zipPath = "$ReportDirectory.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $ReportDirectory "*") -DestinationPath $zipPath -CompressionLevel Optimal

    Write-Host ""
    Write-Host "SETAD live-test report package:" -ForegroundColor Green
    Write-Host $zipPath -ForegroundColor White
    Write-Host "The pre-test database backup remains separate at:" -ForegroundColor DarkGreen
    Write-Host $backupPath -ForegroundColor White

    if ($testExitCode -ne 0) {
        Write-Host "The controlled test reported a connector failure. Upload the report ZIP for analysis." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit $testExitCode
    }

    Write-Host "The controlled SETAD test completed successfully." -ForegroundColor Green
    Read-Host "Press Enter to close"
} finally {
    if ($CopiedTemporaryEnv -and (Test-Path -LiteralPath $LocalEnvPath)) {
        Remove-Item -LiteralPath $LocalEnvPath -Force -ErrorAction SilentlyContinue
    }
}
