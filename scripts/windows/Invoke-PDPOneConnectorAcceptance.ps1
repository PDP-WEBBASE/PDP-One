#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1, 10)]
    [int]$HezarehParsnamadPages = 3,

    [ValidateRange(1, 5)]
    [int]$SetadPages = 2,

    [string]$ProjectRoot = "",

    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Read-JsonReport([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    return ($text | ConvertFrom-Json)
}

function Read-SafeText([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    return (ConvertTo-PDPOneRedactedText (Get-Content -LiteralPath $Path -Raw -Encoding UTF8))
}

function New-PreTestDatabaseBackup(
    [string]$ProjectRoot,
    [string]$EnvironmentPath,
    [string]$Timestamp
) {
    $dbUser = Get-PDPOneEnvValue $EnvironmentPath "POSTGRES_USER"
    $dbName = Get-PDPOneEnvValue $EnvironmentPath "POSTGRES_DB"
    if ($dbUser -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $dbName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Database identifiers are not safe for the connector acceptance backup."
    }

    $preferredRoot = "D:\BackUp PDP-0NE-14050429-01"
    if (Test-Path -LiteralPath "D:\") {
        New-Item -ItemType Directory -Force -Path $preferredRoot | Out-Null
        $backupRoot = $preferredRoot
    } else {
        $backupRoot = Join-Path $AgentRoot "connector-tests\backups"
        New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    }

    $backupPath = Join-Path $backupRoot ("PDP-ONE-PRE-CONNECTOR-ACCEPTANCE-" + $Timestamp + ".dump")
    $command = "docker compose exec -T db pg_dump --username $dbUser --dbname $dbName --format custom > `"$backupPath`""
    cmd.exe /d /s /c $command
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath)) {
        throw "The pre-test PostgreSQL backup failed. Connector tests were not started."
    }
    if ((Get-Item -LiteralPath $backupPath).Length -le 0) {
        throw "The pre-test PostgreSQL backup is empty. Connector tests were not started."
    }
    return $backupPath
}

function Invoke-ConnectorCommand(
    [string[]]$Arguments,
    [string]$StdoutPath,
    [string]$StderrPath
) {
    $output = @(& docker @Arguments 2> $StderrPath)
    $exitCode = $LASTEXITCODE
    [IO.File]::WriteAllLines($StdoutPath, [string[]]$output, [Text.UTF8Encoding]::new($false))
    return $exitCode
}

function Convert-ConnectorRows($Report, [int]$SampleLimit = 3) {
    $rows = @()
    if ($null -eq $Report -or $null -eq $Report.connectors) { return $rows }
    foreach ($connector in @($Report.connectors)) {
        $samples = @($connector.sample_records | Select-Object -First $SampleLimit)
        $errors = @($connector.errors)
        $tested = $true
        if ($null -ne $connector.PSObject.Properties["tested"]) { $tested = [bool]$connector.tested }
        $acceptance = "passed"
        if (-not $tested) {
            $acceptance = "skipped-disabled"
        } elseif ($errors.Count -gt 0) {
            $acceptance = "needs-review"
        } elseif ($samples.Count -eq 0) {
            $acceptance = "needs-review-no-sample"
        }
        $rows += [ordered]@{
            key = [string]$connector.key
            source = if ($null -ne $connector.PSObject.Properties["source"]) { [string]$connector.source } else { "setad" }
            notice_type = if ($null -ne $connector.PSObject.Properties["notice_type"]) { [string]$connector.notice_type } else { "" }
            tested = $tested
            enabled = [bool]$connector.enabled
            status = [string]$connector.status
            parser_version = [string]$connector.parser_version
            requested_pages = if ($null -ne $connector.PSObject.Properties["requested_pages"]) { [int]$connector.requested_pages } else { 0 }
            acceptance = $acceptance
            summary = $connector.summary
            sample_records = $samples
            errors = $errors
        }
    }
    return $rows
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Get-PDPOneProjectRoot
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}
$environmentPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
Set-Location $ProjectRoot

if (-not (Test-PDPOneDockerEngine)) {
    throw "Docker is not ready. Connector acceptance was not started."
}

$requiredServices = @(& docker compose ps --status running --services 2>$null)
foreach ($service in @("db", "redis", "backend")) {
    if ($requiredServices -notcontains $service) {
        throw "Required PDP One service is not running: $service"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDirectory = Join-Path $AgentRoot ("connector-tests\PDP-ONE-CONNECTOR-ACCEPTANCE-" + $timestamp)
New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null

$hpJsonPath = Join-Path $reportDirectory "hezareh-parsnamad.json"
$hpErrorPath = Join-Path $reportDirectory "hezareh-parsnamad.stderr.txt"
$setadJsonPath = Join-Path $reportDirectory "setad.json"
$setadErrorPath = Join-Path $reportDirectory "setad.stderr.txt"
$combinedPath = Join-Path $reportDirectory "PDP-ONE-CONNECTOR-ACCEPTANCE-REPORT.json"

$backupPath = New-PreTestDatabaseBackup -ProjectRoot $ProjectRoot -EnvironmentPath $environmentPath -Timestamp $timestamp

$hpExitCode = Invoke-ConnectorCommand -Arguments @(
    "compose", "exec", "-T", "backend", "python", "manage.py",
    "test_hezareh_parsnamad_connectors", "--pages", ([string]$HezarehParsnamadPages)
) -StdoutPath $hpJsonPath -StderrPath $hpErrorPath

$hpReport = Read-JsonReport $hpJsonPath

$setadExitCode = Invoke-ConnectorCommand -Arguments @(
    "compose", "exec", "-T", "backend", "python", "manage.py",
    "test_setad_connectors", "--pages", ([string]$SetadPages), "--connector", "all"
) -StdoutPath $setadJsonPath -StderrPath $setadErrorPath

$setadReport = Read-JsonReport $setadJsonPath

$hpRows = @(Convert-ConnectorRows $hpReport)
$setadRows = @(Convert-ConnectorRows $setadReport)
$allRows = @($hpRows + $setadRows)

$overallStatus = "passed"
if ($null -eq $hpReport -and $null -eq $setadReport) {
    $overallStatus = "failed"
} elseif ($hpExitCode -ne 0 -or $setadExitCode -ne 0 -or @($allRows | Where-Object { $_.acceptance -like "needs-review*" }).Count -gt 0) {
    $overallStatus = "partial"
}

$combined = [ordered]@{
    schema = "pdp-one.connector-acceptance.v1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    overall_status = $overallStatus
    page_caps = [ordered]@{
        hezareh_parsnamad = $HezarehParsnamadPages
        setad = $SetadPages
    }
    safety = [ordered]@{
        public_list_only = $true
        include_details = $false
        analyze_after_success = $false
        captcha_bypass = $false
        browser_cookie_used = $false
        volumes_touched = $false
        application_replaced = $false
        parsnamad_tenders_respects_enabled_state = $true
    }
    pre_test_backup = [ordered]@{
        path = $backupPath
        size_bytes = [int64](Get-Item -LiteralPath $backupPath).Length
    }
    groups = [ordered]@{
        hezareh_parsnamad = [ordered]@{
            command_exit_code = $hpExitCode
            run_id = if ($null -ne $hpReport) { [string]$hpReport.run_id } else { "" }
            run_status = if ($null -ne $hpReport) { [string]$hpReport.run_status } else { "report-missing" }
            totals = if ($null -ne $hpReport) { $hpReport.totals } else { $null }
            skipped_disabled_connector_keys = if ($null -ne $hpReport) { @($hpReport.skipped_disabled_connector_keys) } else { @() }
            connectors = $hpRows
            safe_command_error = Read-SafeText $hpErrorPath
        }
        setad = [ordered]@{
            command_exit_code = $setadExitCode
            run_id = if ($null -ne $setadReport) { [string]$setadReport.run_id } else { "" }
            run_status = if ($null -ne $setadReport) { [string]$setadReport.run_status } else { "report-missing" }
            totals = if ($null -ne $setadReport) { $setadReport.totals } else { $null }
            connectors = $setadRows
            safe_command_error = Read-SafeText $setadErrorPath
        }
    }
    connector_results = $allRows
}

$combined | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $combinedPath -Encoding UTF8
Write-Output $combinedPath

if ($overallStatus -eq "failed") { exit 1 }
exit 0
