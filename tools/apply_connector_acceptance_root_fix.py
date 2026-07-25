from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "windows" / "Invoke-PDPOneConnectorAcceptance.ps1"
AGENT = ROOT / "scripts" / "windows" / "Deployment-Agent.ps1"
INSTALLER = ROOT / "scripts" / "windows" / "Install-PDPOneDeploymentAgent.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-connector-acceptance-root-fix.yml"
SELF = Path(__file__).resolve()

runner = RUNNER.read_text(encoding="utf-8-sig")
if "[string]$ProjectRoot = \"\"" not in runner:
    runner = runner.replace(
        '    [ValidateRange(1, 5)]\n    [int]$SetadPages = 2,\n\n    [string]$AgentRoot',
        '    [ValidateRange(1, 5)]\n    [int]$SetadPages = 2,\n\n    [string]$ProjectRoot = "",\n\n    [string]$AgentRoot',
        1,
    )
runner = runner.replace(
    '$projectRoot = Get-PDPOneProjectRoot\n$environmentPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot\nSet-Location $projectRoot',
    'if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {\n    $ProjectRoot = Get-PDPOneProjectRoot\n} else {\n    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path\n}\n$environmentPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot\nSet-Location $ProjectRoot',
    1,
)
runner = runner.replace(
    'New-PreTestDatabaseBackup -ProjectRoot $projectRoot -EnvironmentPath',
    'New-PreTestDatabaseBackup -ProjectRoot $ProjectRoot -EnvironmentPath',
    1,
)
RUNNER.write_text(runner, encoding="utf-8-sig")

agent = AGENT.read_text(encoding="utf-8-sig")
agent = agent.replace(
    '                "-SetadPages", "2",\n                "-AgentRoot", $AgentRoot\n',
    '                "-SetadPages", "2",\n                "-AgentRoot", $AgentRoot,\n                "-ProjectRoot", $ProjectRoot\n',
    1,
)
agent = agent.replace(
    '                "-SetadPages", ([string]$setadPages),\n                "-AgentRoot", $AgentRoot\n',
    '                "-SetadPages", ([string]$setadPages),\n                "-AgentRoot", $AgentRoot,\n                "-ProjectRoot", $ProjectRoot\n',
    1,
)
AGENT.write_text(agent, encoding="utf-8-sig")

installer = INSTALLER.read_text(encoding="utf-8-sig")
if '"Invoke-PDPOneConnectorAcceptance.ps1"' not in installer:
    installer = installer.replace(
        '    "Invoke-PDPOneDiskMaintenance.ps1"\n',
        '    "Invoke-PDPOneDiskMaintenance.ps1", "Invoke-PDPOneConnectorAcceptance.ps1"\n',
        1,
    )
INSTALLER.write_text(installer, encoding="utf-8-sig")

for temporary in (WORKFLOW, SELF):
    if temporary.exists():
        temporary.unlink()
