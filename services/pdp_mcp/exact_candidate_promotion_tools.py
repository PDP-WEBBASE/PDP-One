"""Governed exact-candidate runtime promotion tools for PDP One.

The MCP surface submits one signed composite promotion request. The Windows
Deployment Agent owns the deployment plus independent post-deployment health so
the workflow survives recreation of the MCP container itself. GitHub merge is
intentionally outside this action and still requires a fresh PRE-MERGE sync.
"""

from __future__ import annotations

from deployment_queue import enqueue, get_queue_status, validate_commit, validate_identifier
from mcp.types import ToolAnnotations


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
        queue_status = get_queue_status()
        if not queue_status.get("configured") or not queue_status.get("queue_available"):
            raise RuntimeError("The signed local Deployment Agent queue is not available.")
        if queue_status.get("low_disk_space"):
            raise RuntimeError("Deployment Agent storage is low; run the governed disk-maintenance path before promotion.")
        if int(queue_status.get("pending_requests", 0)) != 0:
            raise RuntimeError("A signed Deployment Agent request is already pending. Refresh PRE-DEPLOY coordination before promotion.")

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
