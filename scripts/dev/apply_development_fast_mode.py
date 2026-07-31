from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_block(text: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:start] + replacement + text[end:]


def patch_agent() -> None:
    path = ROOT / "scripts/windows/Deployment-Agent.ps1"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '$restartAfterResponse = $false\n',
        '$restartAfterResponse = $false\n$script:PDPOneChangeManagementMode = "standard"\n\nfunction Test-PDPOneDevelopmentFastMode {\n    return $script:PDPOneChangeManagementMode -eq "development_fast"\n}\n',
        "agent mode declaration",
    )
    deploy_block = r'''        "deploy_approved_release" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $previewId = Assert-SafeIdentifier ([string]$params.preview_id) "preview_id"
            $commit = [string]$params.commit_sha
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Deployment commit is invalid." }
            $developmentFast = Test-PDPOneDevelopmentFastMode
            $approvalPath = Join-Path $AgentRoot "state\approved-release.json"
            $backupStatePath = Join-Path $AgentRoot "state\approved-backup.json"
            $verifiedBackupPath = ""
            $verifiedBackupId = ""

            if (-not $developmentFast) {
                if (-not (Test-Path -LiteralPath $approvalPath)) { throw "No explicit release approval is recorded." }
                $approval = Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([DateTimeOffset]::Parse($approval.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Release approval expired." }
                if ($approval.commit_sha -ne $commit -or $approval.preview_id -ne $previewId) { throw "Requested deployment does not match the approved preview." }

                if (-not (Test-Path -LiteralPath $backupStatePath)) { throw "No fresh verified final backup is recorded for this deployment." }
                $backupState = Get-Content -LiteralPath $backupStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([DateTimeOffset]::Parse($backupState.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Verified final backup authorization expired." }
                if ([string]$backupState.commit_sha -ne $commit) { throw "Verified final backup commit does not match the approved deployment." }
                if ([string]$backupState.deployment_id -ne $deploymentId) { throw "Verified final backup deployment identifier does not match." }
                if (-not [bool]$backupState.restore_verified -or -not (Test-Path -LiteralPath ([string]$backupState.backup_path))) { throw "Verified final backup is not available." }
                $verifiedBackupPath = [string]$backupState.backup_path
                $verifiedBackupId = [string]$backupState.backup_id
            }

            $deploymentArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Invoke-PDPOneDeployment.ps1"),
                "-CommitSha", $commit,
                "-DeploymentId", $deploymentId,
                "-PreviewId", $previewId,
                "-AgentRoot", $AgentRoot
            )
            if ($developmentFast) {
                $deploymentArgs += "-DevelopmentFastMode"
            } else {
                $deploymentArgs += @("-VerifiedBackupPath", $verifiedBackupPath)
            }
            $report = @(& powershell.exe @deploymentArgs)
            if ($LASTEXITCODE -ne 0) { throw "Deployment failed; see the rollback result in the deployment report." }
            Remove-Item -LiteralPath $approvalPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $backupStatePath -Force -ErrorAction SilentlyContinue
            return @{
                deployment_id = $deploymentId
                commit_sha = $commit
                status = "healthy"
                report = ([string]$report[-1])
                change_management_mode = $(if ($developmentFast) { "development_fast" } else { "standard" })
                backup_skipped = [bool]$developmentFast
                reused_verified_backup = $verifiedBackupId
            }
        }
'''
    text = replace_block(
        text,
        '        "deploy_approved_release" {',
        '        "check_deployment_health" {',
        deploy_block,
        "agent deploy action",
    )
    rollback_block = r'''        "rollback_deployment" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $statePath = Join-Path $AgentRoot "state\last-deployment.json"
            if (-not (Test-Path -LiteralPath $statePath)) { throw "No deployment state is available for rollback." }
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.deployment_id -ne $deploymentId) { throw "Rollback deployment identifier does not match." }
            $rollbackArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Rollback-PDPOne.ps1"),
                "-BackupPath", ([string]$state.backup_path),
                "-CodeArchive", ([string]$state.code_archive),
                "-Automatic"
            )
            $mode = if ($null -ne $state.PSObject.Properties["change_management_mode"]) { [string]$state.change_management_mode } else { "standard" }
            if ($mode -ne "development_fast") { $rollbackArgs += "-RestoreDatabase" }
            & powershell.exe @rollbackArgs
            if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }
            return @{ deployment_id = $state.deployment_id; rollback = "healthy"; change_management_mode = $mode; reason = (ConvertTo-PDPOneRedactedText ([string]$params.reason)) }
        }
'''
    text = replace_block(
        text,
        '        "rollback_deployment" {',
        '        "rotate_mcp_token" {',
        rollback_block,
        "agent rollback action",
    )
    mode_anchor = '        $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot\n        $signingKey = Get-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_SIGNING_KEY"\n'
    mode_replacement = '''        $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
        $configuredChangeMode = [string](Get-PDPOneEnvValue $envPath "PDP_CHANGE_MANAGEMENT_MODE")
        $trialModeValue = [string](Get-PDPOneEnvValue $envPath "PDP_TRIAL_MODE")
        if ([string]::IsNullOrWhiteSpace($configuredChangeMode)) {
            $script:PDPOneChangeManagementMode = $(if ($trialModeValue.ToLowerInvariant() -in @("1", "true", "yes")) { "development_fast" } else { "standard" })
        } elseif ($configuredChangeMode -in @("development_fast", "standard")) {
            $script:PDPOneChangeManagementMode = $configuredChangeMode
        } else {
            throw "PDP_CHANGE_MANAGEMENT_MODE must be development_fast or standard."
        }
        $signingKey = Get-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_SIGNING_KEY"
'''
    text = replace_once(text, mode_anchor, mode_replacement, "agent mode resolution")
    path.write_text(text, encoding="utf-8")


def patch_deployment() -> None:
    path = ROOT / "scripts/windows/Invoke-PDPOneDeployment.ps1"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    [Parameter(Mandatory = $true)][string]$AgentRoot,\n    [string]$VerifiedBackupPath = ""\n',
        '    [Parameter(Mandatory = $true)][string]$AgentRoot,\n    [string]$VerifiedBackupPath = "",\n    [switch]$DevelopmentFastMode\n',
        "deployment parameter",
    )
    text = replace_once(
        text,
        '    production_changed = $false\n',
        '    production_changed = $false\n    change_management_mode = $(if ($DevelopmentFastMode) { "development_fast" } else { "standard" })\n    backup_skipped = [bool]$DevelopmentFastMode\n',
        "deployment report mode",
    )
    backup_replacement = r'''    $attemptState.stage = $(if ($DevelopmentFastMode) { "preparing-code-only-rollback" } else { "validating-final-backup" })
    $attemptState | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($DevelopmentFastMode) {
        $rollbackRoot = Join-Path $AgentRoot "rollback\$DeploymentId"
        if (Test-Path -LiteralPath $rollbackRoot) { Remove-Item -LiteralPath $rollbackRoot -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $rollbackRoot | Out-Null
        $backupPath = $rollbackRoot
        $attemptState.backup_path = $null
    } elseif ($VerifiedBackupPath) {
        $backupRoot = "C:\ProgramData\PDP-One\backups"
        if (-not (Test-Path -LiteralPath $backupRoot)) { throw "The verified backup root does not exist." }
        $resolvedRoot = (Resolve-Path -LiteralPath $backupRoot).Path.TrimEnd('\')
        $resolvedBackup = (Resolve-Path -LiteralPath $VerifiedBackupPath).Path.TrimEnd('\')
        if (-not $resolvedBackup.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Verified backup path is outside the protected backup root." }
        $backupReportPath = Join-Path $resolvedBackup "backup-report.json"
        if (-not (Test-Path -LiteralPath $backupReportPath)) { throw "Verified backup report is missing." }
        $backupReport = Get-Content -LiteralPath $backupReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not [bool]$backupReport.restore_verified) { throw "The supplied backup has not passed restore verification." }
        if ([string]$backupReport.approved_commit -ne $CommitSha) { throw "Verified backup commit does not match the approved deployment commit." }
        if ([string]$backupReport.deployment_id -ne $DeploymentId) { throw "Verified backup deployment identifier does not match." }
        $backupPath = $resolvedBackup
        $attemptState.backup_path = $backupPath
    } else {
        $backupOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "New-PDPOneBackup.ps1") -Kind final -DeploymentId $DeploymentId -ApprovedCommit $CommitSha)
        if ($LASTEXITCODE -ne 0) { throw "Final backup creation failed. Deployment was not started." }
        $backupPath = [string]$backupOutput[-1]
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-PDPOneBackupRestore.ps1") -BackupPath $backupPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Final backup restore verification failed. Deployment was not started." }
        $attemptState.backup_path = $backupPath
    }
'''
    text = replace_block(
        text,
        '    $attemptState.stage = "validating-final-backup"',
        '    $attemptState.stage = "snapshotting-current-code"',
        backup_replacement,
        "deployment backup section",
    )
    text = replace_once(
        text,
        '        status = "updating"\n',
        '        status = "updating"\n        change_management_mode = $(if ($DevelopmentFastMode) { "development_fast" } else { "standard" })\n',
        "deployment state mode",
    )
    update_old = '    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Update-PDPOne.ps1") -SourceRoot $sourceRoot.FullName -InstalledRoot $ProjectRoot -ApprovedCommit $CommitSha -DeploymentId $DeploymentId -BackupPath $backupPath -CodeArchive $codeArchive -AgentAuthorized\n'
    update_new = '''    $updateArgs = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "Update-PDPOne.ps1"),
        "-SourceRoot", $sourceRoot.FullName,
        "-InstalledRoot", $ProjectRoot,
        "-ApprovedCommit", $CommitSha,
        "-DeploymentId", $DeploymentId,
        "-BackupPath", $backupPath,
        "-CodeArchive", $codeArchive,
        "-AgentAuthorized"
    )
    if ($DevelopmentFastMode) { $updateArgs += "-DevelopmentFastMode" }
    & powershell.exe @updateArgs
'''
    text = replace_once(text, update_old, update_new, "deployment updater invocation")
    path.write_text(text, encoding="utf-8")


def patch_update() -> None:
    path = ROOT / "scripts/windows/Update-PDPOne.ps1"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    [string]$CodeArchive = "",\n    [switch]$AgentAuthorized\n',
        '    [string]$CodeArchive = "",\n    [switch]$AgentAuthorized,\n    [switch]$DevelopmentFastMode\n',
        "update parameter",
    )
    text = replace_once(
        text,
        '    if ($ApprovedCommit -notmatch \'^[0-9a-f]{40}$\' -or -not $DeploymentId -or -not $BackupPath -or -not $CodeArchive) {\n        throw "Agent-authorized update is missing its locked commit, deployment, backup, or rollback snapshot."\n    }\n',
        '    if ($ApprovedCommit -notmatch \'^[0-9a-f]{40}$\' -or -not $DeploymentId -or -not $CodeArchive -or (-not $DevelopmentFastMode -and -not $BackupPath)) {\n        throw "Agent-authorized update is missing its locked commit, deployment, or rollback snapshot."\n    }\n',
        "update authorization",
    )
    text = replace_once(
        text,
        '$backupReport = Get-Content -LiteralPath (Join-Path $BackupPath "backup-report.json") -Raw | ConvertFrom-Json\nif (-not $backupReport.restore_verified) { throw "Update is blocked: the linked backup has not passed restore verification." }\n',
        '$backupReport = $null\nif (-not $DevelopmentFastMode) {\n    $backupReport = Get-Content -LiteralPath (Join-Path $BackupPath "backup-report.json") -Raw | ConvertFrom-Json\n    if (-not $backupReport.restore_verified) { throw "Update is blocked: the linked backup has not passed restore verification." }\n}\n',
        "update backup verification",
    )
    text = replace_once(
        text,
        '        if ($migrationAttempted) { $rollbackArgs += "-RestoreDatabase" }\n',
        '        if ($migrationAttempted -and -not $DevelopmentFastMode) { $rollbackArgs += "-RestoreDatabase" }\n',
        "update rollback database",
    )
    text = replace_once(
        text,
        '$diagnosticBackupId = $(if ($null -ne $backupReport -and -not [string]::IsNullOrWhiteSpace([string]$backupReport.backup_id)) { [string]$backupReport.backup_id } else { "unknown-backup" })\n',
        '$diagnosticBackupId = $(if ($DevelopmentFastMode) { "development-fast-no-database-backup" } elseif ($null -ne $backupReport -and -not [string]::IsNullOrWhiteSpace([string]$backupReport.backup_id)) { [string]$backupReport.backup_id } else { "unknown-backup" })\n',
        "update diagnostics",
    )
    maintenance_old = '        $maintenanceOutput = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstalledRoot "scripts\\windows\\Invoke-PDPOneDiskMaintenance.ps1") -Mode post-deployment -KeepLocalFinalBackups 2 -ProtectedBackupPath $BackupPath)\n'
    maintenance_new = '''        $maintenanceArgs = @(
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $InstalledRoot "scripts\windows\Invoke-PDPOneDiskMaintenance.ps1"),
            "-Mode", "post-deployment",
            "-KeepLocalFinalBackups", "2"
        )
        if (-not $DevelopmentFastMode) { $maintenanceArgs += @("-ProtectedBackupPath", $BackupPath) }
        $maintenanceOutput = @(& powershell.exe @maintenanceArgs)
'''
    text = replace_once(text, maintenance_old, maintenance_new, "update maintenance")
    path.write_text(text, encoding="utf-8")


def patch_server() -> None:
    path = ROOT / "services/pdp_mcp/server.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'TOKEN = os.getenv("PDP_MCP_TOKEN", "")\n',
        'TOKEN = os.getenv("PDP_MCP_TOKEN", "")\n\n\ndef development_fast_mode() -> bool:\n    configured = os.getenv("PDP_CHANGE_MANAGEMENT_MODE", "").strip().lower()\n    if configured:\n        return configured == "development_fast"\n    return os.getenv("PDP_TRIAL_MODE", "false").strip().lower() in {"1", "true", "yes"}\n',
        "server mode helper",
    )
    prepare_start = '@mcp.tool(\n    description="Return the mandatory guarded workflow for a proposed web change. Source changes still occur only on a separate GitHub branch.",'
    prepare_end = '@mcp.tool(\n    description="Return the Preview gate requirements. It does not deploy or modify the Windows installation.",'
    prepare_block = '''@mcp.tool(
    description="Return the active change-management workflow. Trial deployments use development-fast mode; non-trial deployments use the standard guarded workflow.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def prepare_web_change(summary: str) -> dict:
    fast = development_fast_mode()
    return {
        "summary": summary,
        "mode": "development_fast" if fast else "standard",
        "workflow": (
            ["branch", "tests", "security review", "deploy", "health", "merge"]
            if fast
            else [
                "branch",
                "tests",
                "security review",
                "preview",
                "explicit approval",
                "final verified backup",
                "deploy",
                "health",
                "rollback on failure",
            ]
        ),
        "standing_deploy_authorization": fast,
        "database_backup_required": not fast,
        "code_snapshot_required": True,
        "production_changed": False,
        "requires_github_branch": True,
        "standard_mode_returns_when_trial_mode_is_disabled": True,
    }


'''
    text = replace_block(text, prepare_start, prepare_end, prepare_block, "server prepare workflow")
    old_preview = '''async def create_preview(commit_sha: str) -> dict:
    commit = validate_commit(commit_sha)
    return {
        "commit_sha": commit,
        "production_changed": False,
        "gate": "stop-for-explicit-user-approval",
        "preview_created_by": "GitHub/Sites workflow",
    }
'''
    new_preview = '''async def create_preview(commit_sha: str) -> dict:
    commit = validate_commit(commit_sha)
    fast = development_fast_mode()
    return {
        "commit_sha": commit,
        "production_changed": False,
        "mode": "development_fast" if fast else "standard",
        "gate": "standing-owner-authorization" if fast else "stop-for-explicit-user-approval",
        "preview_created_by": "GitHub/Sites workflow",
        "database_backup_required": not fast,
    }
'''
    text = replace_once(text, old_preview, new_preview, "server preview")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_agent()
    patch_deployment()
    patch_update()
    patch_server()


if __name__ == "__main__":
    main()
