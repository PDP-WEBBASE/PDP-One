from pathlib import Path

path = Path("services/pdp_mcp/server.py")
text = path.read_text(encoding="utf-8")
marker = '''@mcp.tool(
    description="Return the local deployment agent and signed-queue status. This never changes the installation.",
'''
if "async def start_connector_acceptance_test" in text:
    raise SystemExit(0)
if marker not in text:
    raise SystemExit("MCP insertion marker was not found")
block = '''@mcp.tool(
    description="Start a bounded real-data acceptance test for each active procurement connector separately. Pars Namad tenders remains disabled. The test preserves all existing data and returns a suite id for polling.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True, idempotentHint=False),
)
async def start_connector_acceptance_test(page_cap: int = 3, lookback_days: int = 7) -> dict:
    return await api(
        "POST",
        "procurement/connector-acceptance/start/",
        json={
            "page_cap": max(2, min(int(page_cap), 5)),
            "lookback_days": max(1, min(int(lookback_days), 30)),
        },
    )


@mcp.tool(
    description="Return the auditable real-data connector acceptance report for one suite, including pages, counts, source links, raw-data samples, standardized-data samples, duplicates, and errors.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_connector_acceptance_report(suite_id: str) -> dict:
    normalized = validate_identifier(suite_id, "suite_id")
    return await api("GET", f"procurement/connector-acceptance/{normalized}/report/")


@mcp.tool(
    description="Close only stale queued or running procurement extraction records while preserving all pages, notices, revisions, and errors already captured. Use when extraction rows remain running without progress.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def repair_stale_connector_runs(max_age_minutes: int = 30) -> dict:
    return await api(
        "POST",
        "procurement/connector-acceptance/repair-stale/",
        json={"max_age_minutes": max(15, min(int(max_age_minutes), 1440))},
    )


'''
path.write_text(text.replace(marker, block + marker, 1), encoding="utf-8")
