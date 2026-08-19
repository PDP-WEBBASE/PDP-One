#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$windowsRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $windowsRoot 'PDPOne.DeploymentStateCompatibility.ps1')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$temporary = Join-Path $env:TEMP ('pdp-one-scoped-state-' + [Guid]::NewGuid().ToString('N'))
$stateRoot = Join-Path $temporary 'state'
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
try {
    $statePath = Join-Path $stateRoot 'last-deployment.json'
    [ordered]@{
        deployment_id = 'legacy-release'
        preview_id = 'legacy-preview'
        approved_commit = ('a' * 40)
        previous_commit = ('b' * 40)
        active_images = [ordered]@{
            backend = 'ghcr.io/pdp-webbase/pdp-one-backend:' + ('a' * 40)
            mcp = 'ghcr.io/pdp-webbase/pdp-one-mcp:' + ('a' * 40)
            web = 'ghcr.io/pdp-webbase/pdp-one-web:' + ('a' * 40)
        }
        status = 'healthy'
        image_source = 'github_container_registry'
        change_management_mode = 'development_fast'
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $statePath -Encoding UTF8

    $changed = Update-PDPOneLegacyDeploymentStateForScopedEngine -AgentRoot $temporary
    Assert-True ([bool]$changed) 'Legacy deployment state was not upgraded.'

    $migrated = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True ($null -ne $migrated.PSObject.Properties['active_release_manifest']) 'active_release_manifest compatibility property is missing.'
    Assert-True ([string]$migrated.active_release_manifest -eq '') 'active_release_manifest compatibility value is not empty.'
    Assert-True ([string]$migrated.previous_release_manifest -eq '') 'previous_release_manifest compatibility value is not empty.'
    Assert-True ([string]$migrated.image_mode -eq 'legacy-exact-sha') 'legacy image mode compatibility value is incorrect.'
    Assert-True ([string]$migrated.approved_commit -eq ('a' * 40)) 'Exact legacy deployed commit changed during state migration.'
    Assert-True ([string]$migrated.active_images.backend -eq ('ghcr.io/pdp-webbase/pdp-one-backend:' + ('a' * 40))) 'Legacy backend image changed during state migration.'

    $second = Update-PDPOneLegacyDeploymentStateForScopedEngine -AgentRoot $temporary
    Assert-True (-not [bool]$second) 'State migration is not idempotent.'

    Write-Host 'Legacy exact-SHA deployment state is safely compatible with the scoped engine on Windows PowerShell 5.1.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
