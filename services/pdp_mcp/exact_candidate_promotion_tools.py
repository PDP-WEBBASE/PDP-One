"""Governed exact-candidate promotion and privileged Windows operations for PDP One.

The MCP surface can submit only fixed signed enum actions. It never accepts
PowerShell, CMD, executable names, arbitrary file paths, or other shell text.
The Windows Deployment Agent independently validates every request.
"""

from __future__ import annotations

import deployment_queue
from deployment_queue import enqueue, get_queue_status, validate_commit, validate_identifier
from mcp.types import ToolAnnotations


_PRIVILEGED_ACTIONS = {
    "sync_agent_from_exact_commit",
    "ensure_pdp_one_started",
    "repair_pdp_one_connectivity",
    "collect_pdp_one_diagnostics",
}
# Keep the single queue signer authoritative while extending it only with this
# fixed enum set. There is still no generic command/action passthrough.
deployment_queue.ALLOWED_ACTIONS.update(_PRIVILEGED_ACTIONS)


def _require_available_empty_queue() -> dict:
    queue_status = get_queue_status()
    if not queue_status.get("configured") or not queue_status.get("queue_available"):
        raise RuntimeError("The signed local Deployment Agent queue is not available.")
    if int(queue_status.get("pending_requests", 0)) != 0:
        raise RuntimeError("A signed Deployment Agent request is already pending. Refresh coordination before submitting another operation.")
    return queue_status


def register_exact_candidate_promotion_tools(mcp, development_fast_mode) -> None:
    @mcp.tool(
        description=(
            "Submit one governed exact-candidate promotion request after exact-head checks and a fresh PRE-DEPLOY "
            "Delta/Concurrency Sync have passed. The signed Windows Deployment Agent performs exact deployment "
            "and an independent post-deployment health check in one durable request, so MCP service recreation "
            "cannot interrupt orchestration. Read the returned request with get_deployment_report until terminal. "
            "The action never merges GitHub and never bypasses PRE-MERGE."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
    )
    async def promote_exact_candidate(commit_sha: str, deployment_id: str, preview_id: str) -> dict:
        if not development_fast_mode():
            raise ValueError("Exact candidate one-command promotion is available only in development-fast mode.")

        commit = validate_commit(commit_sha)
        deployment = validate_identifier(deployment_id, "deployment_id")
        preview = validate_identifier(preview_id, "preview_id")
        queue_status = _require_available_empty_queue()
        if queue_status.get("low_disk_space"):
            raise RuntimeError("Deployment Agent storage is low; run the governed disk-maintenance path before promotion.")

        request = enqueue(
            "promote_exact_candidate",
            {
                "commit_sha": commit,
                "deployment_id": deployment,
                "preview_id": preview,
            },
        )
        return {
            **request,
            "exact_commit": commit,
            "deployment_id": deployment,
            "durable_windows_orchestration": True,
            "includes_independent_health": True,
            "compatibility_preflight_enforced_by_runtime": True,
            "automatic_merge": False,
            "premerge_required_after_runtime_acceptance": True,
            "next_step": "Read this request to terminal state. Merge only after runtime_accepted=true and a fresh PRE-MERGE Delta/Concurrency Sync.",
        }

    @mcp.tool(
        description=(
            "Synchronize only the deployment-agent bootstrap PowerShell files declared by one exact PDP-One commit's "
            "compatibility manifest into the protected Windows Agent. The Agent verifies the exact commit, fixed repository, "
            "manifest schema, allowed scripts/windows paths, PowerShell parsing, hashes, backup/rollback, and schedules its own "
            "restart after the signed response. No arbitrary command or path is accepted."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def sync_deployment_agent_from_exact_commit(commit_sha: str) -> dict:
        commit = validate_commit(commit_sha)
        _require_available_empty_queue()
        request = enqueue(
            "sync_agent_from_exact_commit",
            {"commit_sha": commit},
            ttl_seconds=1800,
        )
        return {
            **request,
            "exact_commit": commit,
            "fixed_repository": "PDP-WEBBASE/PDP-One",
            "arbitrary_shell_allowed": False,
            "agent_restart_after_response": True,
            "next_step": "Read this request to terminal state, then refresh Deployment Agent status before deployment.",
        }

    @mcp.tool(
        description=(
            "Ask the signed Windows Agent to run PDP One's fixed stable-start script. This accepts no command text, "
            "does not reset data or credentials, and is intended for normal owner-directed startup recovery."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def ensure_pdp_one_started() -> dict:
        _require_available_empty_queue()
        return enqueue("ensure_pdp_one_started", {})

    @mcp.tool(
        description=(
            "Run the fixed bounded PDP One connectivity repair through the signed Windows Agent. It accepts no shell text, "
            "does not reset Tailscale identity or MCP credentials, and uses one bounded repair attempt."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def repair_pdp_one_connectivity() -> dict:
        _require_available_empty_queue()
        return enqueue("repair_pdp_one_connectivity", {}, ttl_seconds=1800)

    @mcp.tool(
        description=(
            "Create PDP One's fixed safe Windows diagnostics through the signed Agent. It accepts no path or command input "
            "and returns only a report filename/status, never environment secrets."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def collect_pdp_one_diagnostics() -> dict:
        _require_available_empty_queue()
        return enqueue("collect_pdp_one_diagnostics", {})
