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
$BackendLogs = Join-Path $ReportDirectory "backend-logs.txt"
$SummaryPath = Join-Path $ReportDirectory "README-RESULTS.txt"

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-EnvValue([string]$Path, [string]$Name) {
    $match = Select-String -LiteralPath $Path -Pattern "^$([regex]::Escape($Name))=(.*)$" |
        Select-Object -Last 1
    if ($null -eq $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim()
}

function Wait-ForBackend {
    foreach ($attempt in 1..90) {
        cmd /c "docker compose exec -T backend python manage.py check >nul 2>&1"
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "PDP One backend did not become ready for the SETAD test."
}

function New-PreTestDatabaseBackup {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw "PDP One .env file was not found."
    }
    $dbUser = Get-EnvValue -Path $envPath -Name "POSTGRES_USER"
    $dbName = Get-EnvValue -Path $envPath -Name "POSTGRES_DB"
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

Write-Host "PDP One - SETAD controlled live test" -ForegroundColor Green
Write-Host "Page cap per connector: $Pages" -ForegroundColor Cyan
Write-Host "Public lists only; details and analysis are disabled." -ForegroundColor DarkGreen

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

New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

docker compose up --detach db redis
if ($LASTEXITCODE -ne 0) { throw "PDP One data services could not be started." }

$backupPath = New-PreTestDatabaseBackup
Write-Host "Pre-test database backup created:" -ForegroundColor Green
Write-Host $backupPath -ForegroundColor White

Write-Host "Building the approved backend code ..." -ForegroundColor Cyan
docker compose build backend
if ($LASTEXITCODE -ne 0) { throw "The backend image could not be built." }

docker compose up --detach --no-deps backend
if ($LASTEXITCODE -ne 0) { throw "The backend service could not be started." }
Wait-ForBackend

Write-Host "Applying controlled database migrations ..." -ForegroundColor Cyan
docker compose exec -T backend python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "The controlled migration failed. Review the backend logs." }

Write-Host "Running SETAD tenders and inquiries tests ..." -ForegroundColor Cyan
$previousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & docker compose exec -T backend python manage.py test_setad_connectors --pages $Pages --connector all 1> $ReportJson 2> $CommandErrors
    $testExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorAction
}

& docker compose logs --tail 250 backend 1> $BackendLogs 2>&1

$summary = @"
PDP ONE - SETAD CONTROLLED LIVE TEST

Generated: $((Get-Date).ToString("o"))
Page cap per connector: $Pages
Details requested: false
ChatGPT analysis requested: false
SETAD source activated: true
Connectors activated: setad_tenders, setad_inquiries

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
