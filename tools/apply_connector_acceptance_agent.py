from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "services" / "pdp_mcp" / "server.py"
AGENT = ROOT / "scripts" / "windows" / "Deployment-Agent.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-connector-acceptance-agent.yml"
SELF = Path(__file__).resolve()

SERVER_MARKER = "async def run_connector_acceptance_test("
AGENT_MARKER = '"run_connector_acceptance_test" {'

server_block = r'''
@mcp.tool(
    description=(
        "Run the controlled real public-list acceptance test for enabled Hezareh and Pars Namad connectors "
        "plus both approved SETAD connectors. A pre-test PostgreSQL dump is created; detail pages, CAPTCHA "
        "bypass, browser cookies, and AI analysis are disabled. Pars Namad tenders remain skipped when disabled."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True, idempotentHint=False),
)
async def run_connector_acceptance_test(
    hezareh_parsnamad_pages: int = 3,
    setad_pages: int = 2,
) -> dict:
    hp_pages = int(hezareh_parsnamad_pages)
    setad_page_cap = int(setad_pages)
    if hp_pages < 1 or hp_pages > 10:
        raise ValueError("hezareh_parsnamad_pages must be between 1 and 10.")
    if setad_page_cap < 1 or setad_page_cap > 5:
        raise ValueError("setad_pages must be between 1 and 5.")
    return enqueue(
        "run_connector_acceptance_test",
        {
            "hezareh_parsnamad_pages": hp_pages,
            "setad_pages": setad_page_cap,
        },
    )


'''

agent_block = r'''
        "run_connector_acceptance_test" {
            $hpPages = [int]$params.hezareh_parsnamad_pages
            $setadPages = [int]$params.setad_pages
            if ($hpPages -lt 1 -or $hpPages -gt 10) { throw "Hezareh/Pars Namad page cap must be between 1 and 10." }
            if ($setadPages -lt 1 -or $setadPages -gt 5) { throw "SETAD page cap must be between 1 and 5." }

            $acceptanceArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Invoke-PDPOneConnectorAcceptance.ps1"),
                "-HezarehParsnamadPages", ([string]$hpPages),
                "-SetadPages", ([string]$setadPages),
                "-AgentRoot", $AgentRoot
            )
            $output = @(& powershell.exe @acceptanceArgs)
            $scriptExitCode = $LASTEXITCODE
            if ($output.Count -eq 0) { throw "Connector acceptance did not return a report path." }
            $reportPath = [string]$output[-1]
            if (-not (Test-Path -LiteralPath $reportPath)) { throw "Connector acceptance report was not created." }
            $result = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
            return @{
                report_path = $reportPath
                overall_status = [string]$result.overall_status
                generated_at = [string]$result.generated_at
                page_caps = $result.page_caps
                safety = $result.safety
                pre_test_backup = $result.pre_test_backup
                groups = $result.groups
                connector_results = @($result.connector_results)
                script_exit_code = $scriptExitCode
            }
        }
'''


def patch_server() -> None:
    text = SERVER.read_text(encoding="utf-8")
    if SERVER_MARKER in text:
        return
    function_index = text.index("async def prepare_web_change")
    decorator_index = text.rfind("@mcp.tool(", 0, function_index)
    if decorator_index < 0:
        raise RuntimeError("prepare_web_change decorator was not found")
    text = text[:decorator_index] + server_block + text[decorator_index:]
    SERVER.write_text(text, encoding="utf-8")


def patch_agent() -> None:
    text = AGENT.read_text(encoding="utf-8-sig")
    if AGENT_MARKER in text:
        return
    marker = '        "rollback_deployment" {'
    if marker not in text:
        raise RuntimeError("rollback_deployment switch marker was not found")
    text = text.replace(marker, agent_block + marker, 1)
    AGENT.write_text(text, encoding="utf-8-sig")


patch_server()
patch_agent()

for temporary in (WORKFLOW, SELF):
    if temporary.exists():
        temporary.unlink()
