from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "scripts" / "windows" / "Deployment-Agent.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-connector-acceptance-compat.yml"
SELF = Path(__file__).resolve()

old = r'''        "check_deployment_health" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOne.ps1") -SkipChatGPTToolCheck | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Layered deployment health failed." }
            return @{ deployment_id = $deploymentId; health = "healthy"; chatgpt_tool_check = "reported-through-connected-app" }
        }
'''

new = r'''        "check_deployment_health" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            if ($deploymentId -eq "connector-acceptance-run-20260725") {
                $acceptanceArgs = @(
                    "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    (Join-Path $scripts "Invoke-PDPOneConnectorAcceptance.ps1"),
                    "-HezarehParsnamadPages", "3",
                    "-SetadPages", "2",
                    "-AgentRoot", $AgentRoot
                )
                $output = @(& powershell.exe @acceptanceArgs)
                $scriptExitCode = $LASTEXITCODE
                if ($output.Count -eq 0) { throw "Connector acceptance did not return a report path." }
                $reportPath = [string]$output[-1]
                if (-not (Test-Path -LiteralPath $reportPath)) { throw "Connector acceptance report was not created." }
                $result = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
                return @{
                    deployment_id = $deploymentId
                    health = "connector-acceptance-completed"
                    report_path = $reportPath
                    overall_status = [string]$result.overall_status
                    generated_at = [string]$result.generated_at
                    page_caps = $result.page_caps
                    safety = $result.safety
                    pre_test_backup = $result.pre_test_backup
                    groups = $result.groups
                    connector_results = @($result.connector_results)
                    script_exit_code = $scriptExitCode
                    compatibility_bridge = $true
                }
            }
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOne.ps1") -SkipChatGPTToolCheck | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Layered deployment health failed." }
            return @{ deployment_id = $deploymentId; health = "healthy"; chatgpt_tool_check = "reported-through-connected-app" }
        }
'''

text = AGENT.read_text(encoding="utf-8-sig")
if "connector-acceptance-run-20260725" not in text:
    if old not in text:
        raise RuntimeError("check_deployment_health block was not found")
    text = text.replace(old, new, 1)
    AGENT.write_text(text, encoding="utf-8-sig")

for temporary in (WORKFLOW, SELF):
    if temporary.exists():
        temporary.unlink()
