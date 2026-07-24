#requires -Version 5.1
[CmdletBinding()]
param([int]$TimeoutSeconds = 300)

$ErrorActionPreference = "SilentlyContinue"
$ProgressPreference = "SilentlyContinue"
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (Wait-PDPOneUrl -Url "http://127.0.0.1:8080/healthz" -TimeoutSeconds $TimeoutSeconds) {
    Start-Process "http://localhost:8080" | Out-Null
    exit 0
}
exit 1
