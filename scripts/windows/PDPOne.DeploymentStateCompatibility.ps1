#requires -Version 5.1
Set-StrictMode -Version Latest

function Update-PDPOneLegacyDeploymentStateForScopedEngine {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$AgentRoot)

    $statePath = Join-Path $AgentRoot "state\last-deployment.json"
    if (-not (Test-Path -LiteralPath $statePath)) { return $false }

    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $state) { throw "Existing deployment state is empty." }

    $approved = $state.PSObject.Properties["approved_commit"]
    if ($null -eq $approved -or [string]$approved.Value -notmatch '^[0-9a-f]{40}$') {
        throw "Existing deployment state does not contain a valid exact commit."
    }

    $images = $state.PSObject.Properties["active_images"]
    if ($null -eq $images -or $null -eq $images.Value) {
        throw "Existing deployment state does not contain active immutable images."
    }

    $changed = $false
    if ($null -eq $state.PSObject.Properties["active_release_manifest"]) {
        $state | Add-Member -NotePropertyName active_release_manifest -NotePropertyValue "" -Force
        $changed = $true
    }
    if ($null -eq $state.PSObject.Properties["previous_release_manifest"]) {
        $state | Add-Member -NotePropertyName previous_release_manifest -NotePropertyValue "" -Force
        $changed = $true
    }
    if ($null -eq $state.PSObject.Properties["image_mode"]) {
        $state | Add-Member -NotePropertyName image_mode -NotePropertyValue "legacy-exact-sha" -Force
        $changed = $true
    }

    if ($changed) {
        $temporary = "$statePath.tmp"
        $state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $statePath -Force
    }
    return $changed
}
