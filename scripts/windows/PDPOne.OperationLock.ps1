Set-StrictMode -Version Latest

function Get-PDPOneDeploymentOperationPath {
    [CmdletBinding()]
    param(
        [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
    )

    return (Join-Path $AgentRoot "state\deployment-in-progress.json")
}

function Read-PDPOneDeploymentOperation {
    [CmdletBinding()]
    param(
        [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
        [switch]$RemoveStale
    )

    $path = Get-PDPOneDeploymentOperationPath -AgentRoot $AgentRoot
    if (-not (Test-Path -LiteralPath $path)) {
        return [pscustomobject]@{ Active = $false; Path = $path; State = $null; Reason = "missing" }
    }

    try {
        $state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $expiresAt = [datetime]::MinValue
        $hasExpiry = [datetime]::TryParse([string]$state.expires_at, [ref]$expiresAt)
        $active = $hasExpiry -and $expiresAt.ToUniversalTime() -gt [DateTime]::UtcNow

        if (-not $active -and $RemoveStale) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }

        return [pscustomobject]@{
            Active = $active
            Path = $path
            State = $state
            Reason = $(if ($active) { "active" } else { "expired" })
        }
    }
    catch {
        if ($RemoveStale) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }
        return [pscustomobject]@{ Active = $false; Path = $path; State = $null; Reason = "invalid" }
    }
}

function Write-PDPOneDeploymentOperation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Lease,
        [string]$Stage = "running",
        [int]$LeaseMinutes = 240
    )

    if ($null -eq $Lease -or -not $Lease.Acquired) {
        throw "A valid deployment-operation lease is required."
    }

    $Lease.State.stage = $Stage
    $Lease.State.heartbeat_at = [DateTime]::UtcNow.ToString("o")
    $Lease.State.expires_at = [DateTime]::UtcNow.AddMinutes([Math]::Max(30, $LeaseMinutes)).ToString("o")

    $directory = Split-Path -Parent $Lease.Path
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = $Lease.Path + "." + [Guid]::NewGuid().ToString("N") + ".tmp"
    $Lease.State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Lease.Path -Force
}

function Enter-PDPOneDeploymentOperation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$DeploymentId,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
        [string]$PreviewId = "",
        [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
        [int]$LeaseMinutes = 240
    )

    $mutex = New-Object Threading.Mutex($false, "Global\PDP-One-Deployment-Operation")
    $acquired = $false
    try {
        $acquired = $mutex.WaitOne(0)
    }
    catch [Threading.AbandonedMutexException] {
        $acquired = $true
    }

    if (-not $acquired) {
        $mutex.Dispose()
        return $null
    }

    $existing = Read-PDPOneDeploymentOperation -AgentRoot $AgentRoot -RemoveStale
    if ($existing.Active) {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
        return $null
    }

    $path = Get-PDPOneDeploymentOperationPath -AgentRoot $AgentRoot
    $state = [ordered]@{
        schema = "pdp-one.deployment-operation.v1"
        operation = "deployment"
        deployment_id = $DeploymentId
        preview_id = $PreviewId
        target_commit = $CommitSha
        stage = "starting"
        process_id = $PID
        computer_name = $env:COMPUTERNAME
        started_at = [DateTime]::UtcNow.ToString("o")
        heartbeat_at = [DateTime]::UtcNow.ToString("o")
        expires_at = [DateTime]::UtcNow.AddMinutes([Math]::Max(30, $LeaseMinutes)).ToString("o")
    }

    $lease = [pscustomobject]@{
        Acquired = $true
        Mutex = $mutex
        Path = $path
        State = $state
    }

    Write-PDPOneDeploymentOperation -Lease $lease -Stage "starting" -LeaseMinutes $LeaseMinutes
    return $lease
}

function Exit-PDPOneDeploymentOperation {
    [CmdletBinding()]
    param($Lease)

    if ($null -eq $Lease) { return }

    try {
        if ($Lease.Path -and (Test-Path -LiteralPath $Lease.Path)) {
            Remove-Item -LiteralPath $Lease.Path -Force -ErrorAction SilentlyContinue
        }
    }
    finally {
        if ($Lease.Acquired -and $null -ne $Lease.Mutex) {
            try { $Lease.Mutex.ReleaseMutex() } catch { }
            $Lease.Mutex.Dispose()
        }
    }
}

function Get-PDPOneInFlightCommit {
    [CmdletBinding()]
    param(
        [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
    )

    $operation = Read-PDPOneDeploymentOperation -AgentRoot $AgentRoot -RemoveStale
    if (-not $operation.Active -or $null -eq $operation.State) { return "" }

    $commit = [string]$operation.State.target_commit
    if ($commit -match '^[0-9a-f]{40}$') { return $commit }
    return ""
}
