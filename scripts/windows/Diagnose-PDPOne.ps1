#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ReportPath = Join-Path $ProjectRoot "pdp-one-diagnostics.txt"

function Write-Report([string]$Text = "") {
    $safeText = $Text
    $safeText = $safeText -replace '(?i)(password|token|secret|authorization)(\s*[:=]\s*)[^\s,;"]+', '$1$2<redacted>'
    $safeText = $safeText -replace '(?i)(https?://)[^/\s:@]+:[^@\s/]+@', '$1<redacted>@'
    Add-Content -LiteralPath $ReportPath -Value $safeText -Encoding UTF8
}

function Write-Section([string]$Title) {
    Write-Report ""
    Write-Report ("=" * 72)
    Write-Report $Title
    Write-Report ("=" * 72)
}

function Invoke-DiagnosticCommand([string]$Label, [string]$Command) {
    Write-Report ""
    Write-Report ("> " + $Label)
    try {
        $output = & $env:ComSpec /d /c "$Command 2>&1"
        if ($null -ne $output) {
            foreach ($line in $output) { Write-Report ([string]$line) }
        }
        Write-Report ("ExitCode: " + $LASTEXITCODE)
    } catch {
        Write-Report ("ERROR: " + $_.Exception.Message)
    }
}

function Add-RancherPaths {
    $candidates = @(
        "C:\Program Files\Rancher Desktop\resources\resources\win32\bin",
        (Join-Path $env:LOCALAPPDATA "Programs\Rancher Desktop\resources\resources\win32\bin")
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and ($env:Path -notlike "*$candidate*")) {
            $env:Path = "$candidate;$env:Path"
        }
    }
}

Set-Content -LiteralPath $ReportPath -Value "PDP One Windows diagnostics 2026.07.18.1" -Encoding UTF8
Write-Report ("Generated: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"))
Write-Report "This report is read-only. Obvious tokens, passwords, and URL credentials are redacted."

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"
Add-RancherPaths

Write-Section "Windows and virtualization"
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Report ("OS: " + $os.Caption + " " + $os.Version + " build " + $os.BuildNumber)
    Write-Report ("Architecture: " + $os.OSArchitecture)
} catch {
    Write-Report ("Operating system query failed: " + $_.Exception.Message)
}
try {
    $system = Get-CimInstance Win32_ComputerSystem
    Write-Report ("HypervisorPresent: " + $system.HypervisorPresent)
} catch {
    Write-Report ("Computer system query failed: " + $_.Exception.Message)
}
try {
    $processors = Get-CimInstance Win32_Processor
    foreach ($processor in $processors) {
        Write-Report ("CPU: " + $processor.Name)
        Write-Report ("VirtualizationFirmwareEnabled: " + $processor.VirtualizationFirmwareEnabled)
        Write-Report ("VMMonitorModeExtensions: " + $processor.VMMonitorModeExtensions)
    }
} catch {
    Write-Report ("Processor query failed: " + $_.Exception.Message)
}

Write-Section "Required Windows features"
foreach ($featureName in @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")) {
    try {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName
        Write-Report ($feature.FeatureName + ": " + $feature.State)
    } catch {
        Write-Report ($featureName + ": query failed - " + $_.Exception.Message)
    }
}

Write-Section "WSL status"
Invoke-DiagnosticCommand "wsl --status" "wsl.exe --status"
Invoke-DiagnosticCommand "wsl --version" "wsl.exe --version"
Invoke-DiagnosticCommand "wsl --list --verbose" "wsl.exe --list --verbose"

Write-Section "Installed commands"
foreach ($commandName in @("wsl.exe", "rdctl.exe", "docker.exe")) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Write-Report ($commandName + ": NOT FOUND")
    } else {
        Write-Report ($commandName + ": " + $command.Source)
    }
}

Write-Section "Rancher Desktop status"
Invoke-DiagnosticCommand "rdctl version" "rdctl.exe version"
Invoke-DiagnosticCommand "rdctl info" "rdctl.exe info"
Invoke-DiagnosticCommand "rdctl list-settings" "rdctl.exe list-settings"
Invoke-DiagnosticCommand "Rancher diagnostic checks" "rdctl.exe api /v1/diagnostic_checks"

Write-Section "Docker status"
Invoke-DiagnosticCommand "docker version" "docker.exe version"
Invoke-DiagnosticCommand "docker context ls" "docker.exe context ls"
Invoke-DiagnosticCommand "docker info" "docker.exe info"

Write-Section "Relevant processes"
try {
    $processes = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match "rancher|wsl|vmmem|docker|moby" } |
        Sort-Object ProcessName, Id |
        Select-Object ProcessName, Id, StartTime, Path
    if ($processes) {
        Write-Report (($processes | Format-Table -AutoSize | Out-String).TrimEnd())
    } else {
        Write-Report "No matching processes found."
    }
} catch {
    Write-Report ("Process query failed: " + $_.Exception.Message)
}

Write-Section "Relevant services"
try {
    $services = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "rancher|wsl|docker|vmcompute|Lxss" -or $_.DisplayName -match "rancher|wsl|docker" } |
        Sort-Object Name |
        Select-Object Status, Name, DisplayName
    if ($services) {
        Write-Report (($services | Format-Table -AutoSize | Out-String).TrimEnd())
    } else {
        Write-Report "No matching services found."
    }
} catch {
    Write-Report ("Service query failed: " + $_.Exception.Message)
}

Write-Section "Recent Rancher Desktop logs"
$logRoots = @(
    (Join-Path $env:LOCALAPPDATA "rancher-desktop"),
    (Join-Path $env:APPDATA "rancher-desktop")
) | Select-Object -Unique

$logFiles = @()
foreach ($logRoot in $logRoots) {
    Write-Report ("Log root: " + $logRoot + " (exists: " + (Test-Path -LiteralPath $logRoot) + ")")
    if (Test-Path -LiteralPath $logRoot) {
        $logFiles += Get-ChildItem -LiteralPath $logRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".log", ".txt") }
    }
}

$logFiles = $logFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 10
if (-not $logFiles) {
    Write-Report "No Rancher Desktop log files were found."
} else {
    foreach ($logFile in $logFiles) {
        Write-Report ""
        Write-Report ("--- " + $logFile.FullName + " | " + $logFile.LastWriteTime + " | " + $logFile.Length + " bytes ---")
        try {
            $lines = Get-Content -LiteralPath $logFile.FullName -Tail 120 -ErrorAction Stop
            foreach ($line in $lines) { Write-Report ([string]$line) }
        } catch {
            Write-Report ("Could not read log: " + $_.Exception.Message)
        }
    }
}

Write-Section "End"
Write-Report ("Report path: " + $ReportPath)

Write-Host ""
Write-Host "Diagnostics completed." -ForegroundColor Green
Write-Host "Report: $ReportPath" -ForegroundColor Cyan
Write-Host "Please send pdp-one-diagnostics.txt in ChatGPT." -ForegroundColor Yellow
Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $ReportPath + '"')
