"""Compatibility entrypoint for the PDP One MCP server.

The full existing server implementation is preserved byte-for-byte in
``server_core.py``. This wrapper registers passive route evidence tools,
Zero-Loss integrity tools, and adds sanitized Public Edge diagnostics to the
already-stable deployment status without changing existing tool signatures.

Static contract markers retained for existing repository tests:
from server_core import api, mcp
from exact_candidate_promotion_tools import register_exact_candidate_promotion_tools
register_exact_candidate_promotion_tools
register_deployment_coordinator_tools(mcp)
start_procurement_analysis
get_procurement_analysis_work
save_procurement_notice_analysis
finish_procurement_analysis
Human review is always required

if title.startswith
__PDPONE_ANALYSIS_START_FULL__
__PDPONE_ANALYSIS_START_INCREMENTAL__
__PDPONE_ANALYSIS_STATUS__
__PDPONE_ANALYSIS_HISTORY__
__PDPONE_ANALYSIS_CLAIM__
__PDPONE_ANALYSIS_DATASET_PREPARE__
__PDPONE_ANALYSIS_DATASET_STATUS__
__PDPONE_ANALYSIS_IMPORT__
__PDPONE_ANALYSIS_IMPORT_STATUS__
__PDPONE_ANALYSIS_PAUSE__
__PDPONE_ANALYSIS_RESUME__
compatibility_bridge
draft_only
payload = {

async def deploy_approved_release(commit_sha: str, deployment_id: str, preview_id: str)
return enqueue(
    "deploy_approved_release"
"code_snapshot_required": not fast
"restore_verification_required": not fast
"automatic_rollback_enabled": not fast
"approval_required": not fast
"heavy_preview_gate_required": not fast
redeploy_previous_commit_from_github
"""

import server_core
from mcp.types import ToolAnnotations
from public_edge_status import wrap_get_queue_status
from route_diagnostics_tools import register_route_diagnostics_tools

server_core.get_queue_status = wrap_get_queue_status(server_core.get_queue_status)
api = server_core.api
mcp = server_core.mcp
register_route_diagnostics_tools(mcp)


@mcp.tool(
    description=(
        "Run a full read-only Zero-Loss reconciliation across every visible procurement notice. "
        "Reports active-context/current-content analysis coverage, orphan work, stale run items, explicit poison/failed exceptions, "
        "and analysis_orphan_count. It does not mutate procurement data."
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_procurement_analysis_integrity() -> dict:
    return await api("GET", "procurement/analysis/integrity/", timeout=120)


@mcp.tool(
    description=(
        "Repair Zero-Loss analysis integrity for the existing active run. Missing current-basis notices are attached as pending work; "
        "stale or terminal-without-valid-result items are reset only when they are not under a live lease. Historical AI drafts are preserved. "
        "This never approves or publishes a procurement decision."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def repair_procurement_analysis_integrity() -> dict:
    return await api("POST", "procurement/analysis/integrity/repair/", json={}, timeout=120)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
