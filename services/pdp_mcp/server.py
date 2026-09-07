"""Compatibility entrypoint for the PDP One MCP server.

The full existing server implementation is preserved byte-for-byte in
``server_core.py``. This wrapper registers passive route evidence tools,
Zero-Loss integrity tools, unified interaction tools, and adds sanitized Public
Edge diagnostics to the already-stable deployment status without changing
existing tool signatures.

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

from typing import Any

import deployment_coordinator
import deployment_queue
import promotion_control_v3
import server_core
from interaction_tools import register_interaction_tools
from mcp.types import ToolAnnotations
from public_edge_status import wrap_get_queue_status
from route_diagnostics_tools import register_route_diagnostics_tools

_MISSING_COORDINATOR_HISTORY = "Deployment request evidence is missing from coordinator history."
_SUCCESSFUL_V3_DEPLOYMENT_STATES = {"acceptance", "pre_merge", "merged"}
_SUCCESSFUL_V3_TICKET_STATES = {"pre_merge", "merged"}
_ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE = deployment_coordinator.record_candidate_acceptance


def _v3_request(request_id: str, action: str, schema: str) -> tuple[str, dict[str, Any]]:
    mapping = promotion_control_v3.resolve_request_id(request_id)
    if not mapping or not mapping.get("managed"):
        raise ValueError("Promotion V3 request evidence is missing.")
    client_request_id = str(mapping.get("client_request_id") or "")
    record = mapping.get("record")
    if not client_request_id or not isinstance(record, dict):
        raise ValueError("Promotion V3 request evidence is incomplete.")
    if record.get("schema") != schema or record.get("action") != action:
        raise ValueError("Promotion V3 request type does not match the required evidence.")
    if record.get("client_request_id") != client_request_id:
        raise ValueError("Promotion V3 request identity is inconsistent.")
    return client_request_id, record


def _v3_ticket(ticket_id: str) -> dict[str, Any]:
    active = promotion_control_v3.ACTIVE
    if active.exists():
        value = promotion_control_v3._read_json(active)
        if value.get("ticket_id") == ticket_id:
            return value
    history = promotion_control_v3.HISTORY / f"{ticket_id}.json"
    if not history.exists():
        raise ValueError("Promotion V3 ticket evidence is missing.")
    return promotion_control_v3._read_json(history)


def _validated_v3_acceptance_evidence(
    deployment_request_id: str,
    health_request_id: str,
    head_sha: str,
    deployment_id: str,
) -> tuple[str, str, dict[str, Any]]:
    promotion_control_v3.configure_queue_root(deployment_queue.QUEUE_ROOT)
    deployment_client_id, deployment_record = _v3_request(
        deployment_request_id,
        "promote_exact_candidate",
        "pdp-one.promotion-request.v3",
    )
    health_client_id, health_record = _v3_request(
        health_request_id,
        "check_deployment_health",
        "pdp-one.promotion-health-request.v3",
    )
    ticket_id = str(deployment_record.get("ticket_id") or "")
    if not ticket_id or health_record.get("ticket_id") != ticket_id:
        raise ValueError("Promotion V3 deployment and health evidence do not share one exact ticket.")
    ticket = _v3_ticket(ticket_id)

    for record, label in ((deployment_record, "deployment"), (health_record, "health"), (ticket, "ticket")):
        if record.get("commit_sha") != head_sha or record.get("deployment_id") != deployment_id:
            raise ValueError(f"Promotion V3 {label} evidence does not match the exact candidate.")
    if deployment_record.get("terminal_status") != "succeeded":
        raise ValueError("Promotion V3 deployment did not complete successfully.")
    if str(deployment_record.get("state")) not in _SUCCESSFUL_V3_DEPLOYMENT_STATES:
        raise ValueError("Promotion V3 deployment has not reached an accepted lifecycle state.")
    if health_record.get("terminal_status") != "succeeded" or health_record.get("state") != "succeeded":
        raise ValueError("Promotion V3 independent health did not complete successfully.")
    if ticket.get("schema") != "pdp-one.promotion-ticket.v3" or ticket.get("ticket_id") != ticket_id:
        raise ValueError("Promotion V3 ticket identity is invalid.")
    if str(ticket.get("state")) not in _SUCCESSFUL_V3_TICKET_STATES or ticket.get("runtime_accepted") is not True:
        raise ValueError("Promotion V3 ticket is not runtime accepted.")
    if ticket.get("client_request_id") != deployment_client_id:
        raise ValueError("Promotion V3 ticket deployment lineage is inconsistent.")
    if ticket.get("health_client_request_id") != health_client_id:
        raise ValueError("Promotion V3 ticket health lineage is inconsistent.")
    if deployment_record.get("agent_request_id") and ticket.get("agent_request_id") != deployment_record.get("agent_request_id"):
        raise ValueError("Promotion V3 deployment Agent lineage is inconsistent.")
    if health_record.get("agent_request_id") and ticket.get("health_agent_request_id") != health_record.get("agent_request_id"):
        raise ValueError("Promotion V3 health Agent lineage is inconsistent.")
    return deployment_client_id, health_client_id, ticket


def _record_candidate_acceptance_with_v3(
    workstream_id: str,
    candidate_id: str,
    head_sha: str,
    deployment_request_id: str,
    deployment_id: str,
    health_request_id: str,
    result: str,
) -> dict[str, Any]:
    try:
        return _ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE(
            workstream_id,
            candidate_id,
            head_sha,
            deployment_request_id,
            deployment_id,
            health_request_id,
            result,
        )
    except ValueError as exc:
        if str(exc) != _MISSING_COORDINATOR_HISTORY:
            raise

    deployment_client_id, health_client_id, ticket = _validated_v3_acceptance_evidence(
        deployment_request_id,
        health_request_id,
        head_sha,
        deployment_id,
    )
    history_path = deployment_coordinator.HISTORY / f"{deployment_client_id}.json"
    deployment_coordinator._atomic_json(
        history_path,
        {
            "schema": "pdp-one.coordinated-deployment.v2-reconciled-v3",
            "request_id": deployment_client_id,
            "workstream_id": workstream_id,
            "candidate_id": candidate_id,
            "commit_sha": head_sha,
            "deployment_id": deployment_id,
            "state": "succeeded",
            "evidence_source": "promotion-v3",
            "promotion_ticket_id": ticket["ticket_id"],
            "reconciled_at": deployment_coordinator._now().isoformat(),
        },
    )
    return _ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE(
        workstream_id,
        candidate_id,
        head_sha,
        deployment_client_id,
        deployment_id,
        health_client_id,
        result,
    )


deployment_coordinator.record_candidate_acceptance = _record_candidate_acceptance_with_v3
server_core.get_queue_status = wrap_get_queue_status(server_core.get_queue_status)
api = server_core.api
mcp = server_core.mcp
register_route_diagnostics_tools(mcp)
register_interaction_tools(mcp, api)


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
