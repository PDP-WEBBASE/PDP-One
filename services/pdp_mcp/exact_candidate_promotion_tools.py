"""Governed exact-candidate runtime promotion tools for PDP One.

This module deliberately does not perform GitHub merge operations. ChatGPT must
complete a fresh PRE-DEPLOY coordination sync before invoking promotion and a
fresh PRE-MERGE sync after runtime acceptance.
"""

from __future__ import annotations

import asyncio

from deployment_queue import enqueue, get_queue_status, get_response, validate_commit, validate_identifier
from mcp.types import ToolAnnotations


async def _wait_for_agent_response(request_id: str, timeout_seconds: int) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        response = get_response(request_id)
        if response.get("status") != "pending":
            return response
        if loop.time() >= deadline:
            return {"request_id": request_id, "status": "pending", "wait_timeout_reached": True}
        await asyncio.sleep(2)


def register_exact_candidate_promotion_tools(mcp, development_fast_mode) -> None:
    @mcp.tool(
        description=(
            "Promote one exact tested commit through the development-fast Runtime path in one governed call. "
            "Use only after exact-head checks and a fresh PRE-DEPLOY Delta/Concurrency Sync have passed. "
            "The call submits the existing signed exact-commit deployment action, waits for its terminal result, "
            "then runs an independent signed health check. It never merges GitHub and never bypasses PRE-MERGE."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
    )
    async def promote_exact_candidate(
        commit_sha: str,
        deployment_id: str,
        preview_id: str,
        wait_timeout_seconds: int = 900,
    ) -> dict:
        if not development_fast_mode():
            raise ValueError("Exact candidate one-command promotion is available only in development-fast mode.")

        commit = validate_commit(commit_sha)
        deployment = validate_identifier(deployment_id, "deployment_id")
        preview = validate_identifier(preview_id, "preview_id")
        timeout = max(60, min(int(wait_timeout_seconds), 1500))

        queue_status = get_queue_status()
        if not queue_status.get("configured") or not queue_status.get("queue_available"):
            raise RuntimeError("The signed local Deployment Agent queue is not available.")
        if queue_status.get("low_disk_space"):
            raise RuntimeError("Deployment Agent storage is low; run the governed disk-maintenance path before promotion.")
        if int(queue_status.get("pending_requests", 0)) != 0:
            raise RuntimeError("A signed Deployment Agent request is already pending. Refresh PRE-DEPLOY coordination before promotion.")

        deploy_request = enqueue(
            "deploy_approved_release",
            {
                "commit_sha": commit,
                "deployment_id": deployment,
                "preview_id": preview,
            },
        )
        deploy_response = await _wait_for_agent_response(deploy_request["request_id"], timeout)
        if deploy_response.get("status") == "pending":
            return {
                "status": "deployment_pending",
                "exact_commit": commit,
                "deployment_id": deployment,
                "deploy_request_id": deploy_request["request_id"],
                "deployment": deploy_response,
                "compatibility_preflight_enforced_by_runtime": True,
                "automatic_merge": False,
                "premerge_required": True,
                "next_step": "Read the deployment request to terminal state, then run independent health before PRE-MERGE.",
            }
        if deploy_response.get("status") != "succeeded":
            return {
                "status": "deployment_failed",
                "exact_commit": commit,
                "deployment_id": deployment,
                "deploy_request_id": deploy_request["request_id"],
                "deployment": deploy_response,
                "compatibility_preflight_enforced_by_runtime": True,
                "automatic_merge": False,
                "premerge_required": False,
            }

        health_request = enqueue(
            "check_deployment_health",
            {"deployment_id": deployment},
            ttl_seconds=1800,
        )
        health_response = await _wait_for_agent_response(health_request["request_id"], timeout)
        runtime_accepted = (
            health_response.get("status") == "succeeded"
            and isinstance(health_response.get("result"), dict)
            and health_response["result"].get("health") == "healthy"
        )
        return {
            "status": "runtime_accepted" if runtime_accepted else "health_not_accepted",
            "exact_commit": commit,
            "deployment_id": deployment,
            "deploy_request_id": deploy_request["request_id"],
            "deployment": deploy_response,
            "health_request_id": health_request["request_id"],
            "independent_health": health_response,
            "compatibility_preflight_enforced_by_runtime": True,
            "automatic_merge": False,
            "premerge_required": bool(runtime_accepted),
            "next_step": (
                "Run a fresh PRE-MERGE Delta/Concurrency Sync and merge only if the PR still has this exact head."
                if runtime_accepted
                else "Do not merge. Diagnose the terminal health result while preserving the exact deployed identity."
            ),
        }
