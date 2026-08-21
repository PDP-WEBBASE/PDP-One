#requires -Version 5.1
Set-StrictMode -Version Latest

function ConvertTo-PDPOneScheduledTaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"')) { throw "Scheduled-task arguments may not contain a quote character." }
    return '"' + $Value + '"'
}

function Get-PDPOneHiddenRunnerPath {
    param([string]$BaseDirectory = $PSScriptRoot)
    $runner = Join-Path $BaseDirectory "Run-PDPOneHidden.vbs"
    if (-not (Test-Path -LiteralPath $runner)) { throw "Hidden scheduled-task launcher was not found." }
    return $runner
}

function New-PDPOneHiddenPowerShellAction {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$ScriptArguments = @(),
        [string]$HiddenRunnerPath = ""
    )
    if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Scheduled-task PowerShell script was not found: $ScriptPath" }
    if (-not $HiddenRunnerPath) { $HiddenRunnerPath = Get-PDPOneHiddenRunnerPath }
    if (-not (Test-Path -LiteralPath $HiddenRunnerPath)) { throw "Hidden scheduled-task launcher was not found." }

    $arguments = @(
        "//B",
        "//NoLogo",
        (ConvertTo-PDPOneScheduledTaskArgument $HiddenRunnerPath),
        (ConvertTo-PDPOneScheduledTaskArgument $ScriptPath)
    )
    foreach ($argument in $ScriptArguments) {
        $arguments += ConvertTo-PDPOneScheduledTaskArgument ([string]$argument)
    }

    return New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot "System32\wscript.exe") -Argument ($arguments -join ' ')
}

function Test-PDPOneScheduledTaskWindowless {
    param(
        [Parameter(Mandatory = $true)]$Task,
        [Parameter(Mandatory = $true)][string]$HiddenRunnerPath
    )
    if ($null -eq $Task.Actions -or @($Task.Actions).Count -lt 1) { return $false }
    foreach ($action in @($Task.Actions)) {
        $executeLeaf = [IO.Path]::GetFileName([string]$action.Execute)
        if (-not [string]::Equals($executeLeaf, "wscript.exe", [StringComparison]::OrdinalIgnoreCase)) { return $false }
        $arguments = [string]$action.Arguments
        if ($arguments.IndexOf($HiddenRunnerPath, [StringComparison]::OrdinalIgnoreCase) -lt 0) { return $false }
        if ($arguments -match '(?i)powershell\.exe') { return $false }
    }
    return $true
}

function Assert-PDPOneScheduledTaskWindowless {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$HiddenRunnerPath
    )
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { throw "Required PDP One Scheduled Task is missing: $TaskName" }
    if (-not (Test-PDPOneScheduledTaskWindowless -Task $task -HiddenRunnerPath $HiddenRunnerPath)) {
        throw "PDP One Scheduled Task is not using the required windowless launcher: $TaskName"
    }
    return $task
}
