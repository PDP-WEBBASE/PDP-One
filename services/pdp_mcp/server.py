import asyncio
import hashlib
import os
from typing import Any

import httpx
from deployment_queue import enqueue, get_queue_status, get_response, validate_commit, validate_identifier
from deployment_coordinator import register_tools as register_deployment_coordinator_tools
from exact_candidate_promotion_tools import register_exact_candidate_promotion_tools
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from procurement_analysis_tools import register_procurement_analysis_tools

API_URL = os.getenv("PDP_API_URL", "http://localhost:8000/api/v1").rstrip("/")
TOKEN = os.getenv("PDP_MCP_TOKEN", "")


def development_fast_mode() -> bool:
    configured = os.getenv("PDP_CHANGE_MANAGEMENT_MODE", "").strip().lower()
    if configured:
        return configured == "development_fast"
    return os.getenv("PDP_TRIAL_MODE", "false").strip().lower() in {"1", "true", "yes"}

mcp = FastMCP(
    "PDP One",
    instructions=(
        "Use read tools before write tools. Create contracts, receivables, payment receipts, and analyses only as drafts. "
        "Never claim a draft is approved or financially final. Use returned record IDs in follow-up calls. "
        "For procurement analysis, start one guarded PDP request, read its work package, save one structured AI draft per notice, "
        "then finish the same request. Human review is always required. "
        "Disk maintenance is an explicit signed action that may remove only unused Docker cache, unused images, stopped containers, "
        "old verified backups beyond retention, and stale deployment staging. It never prunes Docker volumes."
    ),
    host="0.0.0.0",
    port=8010,
)


async def api(method: str, path: str, **kwargs: Any) -> Any:
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, f"{API_URL}/{path.lstrip('/')}", headers=headers, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                payload = exc.response.json()
                detail = str(payload.get("detail", "")) if isinstance(payload, dict) else ""
            except ValueError:
                detail = ""
            suffix = f": {detail}" if detail else "."
            raise RuntimeError(f"PDP One API request failed with HTTP {exc.response.status_code}{suffix}") from exc
        return response.json()


register_procurement_analysis_tools(mcp, api)
register_exact_candidate_promotion_tools(mcp, development_fast_mode)
register_deployment_coordinator_tools(mcp)


@mcp.tool(
    description="Check whether PDP One, its PostgreSQL database, and the trial dataset are reachable.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_system_status() -> dict:
    return await api("GET", "system-status/")


@mcp.tool(
    description="Use this when the user wants to find PDP One contracts by code, title, employer, or field.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def search_contracts(query: str = "", status: str | None = None) -> dict:
    params = {"search": query}
    if status:
        params["status"] = status
    result = await api("GET", "contracts/", params=params)
    items = result.get("results", result) if isinstance(result, dict) else result
    return {"contracts": items, "count": len(items)}


@mcp.tool(
    description="Use this when the user asks for a current management summary of PDP One contracts and risks.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_management_summary() -> dict:
    return await api("GET", "management-summary/")


@mcp.tool(
    description="Use this when the user wants to search PDP One receivables, statements, employers, or finance references.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def search_receivables(query: str = "", status: str | None = None, contract_code: str | None = None) -> dict:
    params = {"search": query}
    if status:
        params["status"] = status
    if contract_code:
        params["contract_code"] = contract_code
    result = await api("GET", "receivables/", params=params)
    items = result.get("results", result) if isinstance(result, dict) else result
    return {"receivables": items, "count": len(items)}


@mcp.tool(
    description="Use this when the user asks for the current persisted PDP One financial and receivables summary.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_financial_summary() -> dict:
    return await api("GET", "financial-summary/")


@mcp.tool(
    description="Use this when the user explicitly asks to register a new contract in PDP One. This always creates a draft for human review.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def create_contract_draft(
    code: str,
    title: str,
    employer: str,
    field: str = "",
    value_rials: int | None = None,
    due_date: str | None = None,
) -> dict:
    payload = {
        "code": code,
        "title": title,
        "employer": employer,
        "field": field,
        "value_rials": value_rials,
        "due_date": due_date,
        "progress": 0,
        "status": "draft",
    }
    return {"draft": await api("POST", "contracts/", json=payload), "requires_human_review": True}


@mcp.tool(
    description="Use this when the user explicitly asks to register a receivable or statement in PDP One. It always creates a finance draft for human review.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def create_receivable_draft(
    contract_code: str,
    contract_title: str,
    employer: str,
    statement_title: str,
    amount_rials: int,
    due_date: str,
    received_rials: int = 0,
) -> dict:
    payload = {
        "contract_code": contract_code,
        "contract_title": contract_title,
        "employer": employer,
        "statement_title": statement_title,
        "amount_rials": amount_rials,
        "received_rials": received_rials,
        "due_date": due_date,
    }
    return {"draft": await api("POST", "receivables/", json=payload), "requires_human_review": True}


@mcp.tool(
    description="Use this when the user explicitly asks to register money received against an existing receivable. It always creates a payment receipt draft and does not finalize accounting.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def create_payment_receipt_draft(
    receivable_id: str,
    amount_rials: int,
    received_date: str,
    tracking_code: str = "",
    note: str = "",
) -> dict:
    payload = {
        "receivable": receivable_id,
        "amount_rials": amount_rials,
        "received_date": received_date,
        "tracking_code": tracking_code,
        "note": note,
    }
    return {"draft": await api("POST", "payment-receipts/", json=payload), "requires_human_review": True}


@mcp.tool(
    description="Start one guarded manual PDP procurement-analysis request using the currently active role, Prompt, keywords, company profile, qualifications, and experience. It does not publish decisions.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def start_procurement_analysis(limit: int = 20, extraction_run_id: str | None = None) -> dict:
    payload: dict[str, Any] = {"trigger": "manual_chatgpt", "limit": max(1, min(int(limit), 50))}
    if extraction_run_id:
        payload["extraction_run"] = extraction_run_id
    result = await api("POST", "procurement/analysis/engine/start/", json=payload)
    return {
        **result,
        "next_step": "Call get_procurement_analysis_work with the returned request id, then save one AI draft per item.",
        "requires_human_review": True,
    }


@mcp.tool(
    description="Read the active context and the next notice work items for one previously started PDP procurement-analysis request. Use this before saving analysis drafts.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_procurement_analysis_work(request_id: str, limit: int = 10) -> dict:
    return await api(
        "GET",
        f"procurement/analysis/engine/requests/{request_id}/work/",
        params={"limit": max(1, min(int(limit), 50))},
    )


@mcp.tool(
    description="Save one structured ChatGPT procurement analysis for a notice in an active PDP batch. The result is always an AI draft and never a final decision.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def save_procurement_notice_analysis(
    notice_id: str,
    batch_id: str,
    is_recommended: bool,
    score: int,
    priority: str,
    fit_for_pdp: str,
    category: str,
    reason: str,
    recommended_action: str,
    confidence: float,
    matched_experience: list[str] | None = None,
    risk_notes: list[str] | None = None,
) -> dict:
    payload = {
        "notice": notice_id,
        "batch": batch_id,
        "is_recommended": bool(is_recommended),
        "score": max(0, min(int(score), 100)),
        "priority": priority,
        "fit_for_pdp": fit_for_pdp,
        "category": category,
        "reason": reason,
        "recommended_action": recommended_action,
        "matched_experience": matched_experience or [],
        "risk_notes": risk_notes or [],
        "confidence": max(0.0, min(float(confidence), 100.0)),
        "raw_output": {"engine": "ChatGPT connected app", "decision_is_draft": True},
    }
    draft = await api("POST", "procurement/analysis-drafts/", json=payload)
    return {"draft": draft, "requires_human_review": True}


@mcp.tool(
    description="Finish one PDP procurement-analysis request after its notice drafts have been saved. Unresolved notice IDs are marked failed; nothing is published automatically.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def finish_procurement_analysis(
    request_id: str,
    failed_notice_ids: list[str] | None = None,
    summary_note: str = "",
) -> dict:
    payload = {
        "failed_notice_ids": failed_notice_ids or [],
        "summary": {"note": summary_note[:1000], "engine": "ChatGPT connected app"},
    }
    return await api("POST", f"procurement/analysis/engine/requests/{request_id}/finish/", json=payload)


@mcp.tool(
    description="List recent procurement notice analysis drafts for human review. This does not approve or publish them.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_recent_procurement_analysis_drafts(review_status: str = "ai_draft", limit: int = 20) -> dict:
    params = {"ordering": "-analyzed_at", "review_status": review_status}
    result = await api("GET", "procurement/analysis-drafts/", params=params)
    items = result.get("results", result) if isinstance(result, dict) else result
    return {"drafts": list(items)[: max(1, min(int(limit), 50))], "requires_human_review": True}


@mcp.tool(
    description="Use this when the user explicitly asks to save a general ChatGPT analysis in PDP One. The result is stored as an AI draft, never as an approved report.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def save_analysis_draft(title: str, summary: str, source_record_ids: list[str]) -> dict:
    # Compatibility bridge for ChatGPT apps whose cached schema predates the
    # dedicated persistent-analysis tools. The official tools remain the
    # primary interface; this bridge keeps existing installed apps operable
    # until their MCP schema is rescanned.
    if title.startswith("__PDPONE_ANALYSIS_"):
        try:
            options = json.loads(summary or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Persistent analysis control summary must be valid JSON.") from exc
        if not isinstance(options, dict):
            raise ValueError("Persistent analysis control summary must be a JSON object.")

        def required_identifier(name: str) -> str:
            value = str(options.get(name) or (source_record_ids[0] if source_record_ids else "")).strip()
            if not value:
                raise ValueError(f"{name} is required.")
            return value
        if title == "__PDPONE_ANALYSIS_START_FULL__":
            result = await api(
                "POST",
                "procurement/analysis/runs/full-pending/start/",
                json={
                    "trigger": "manual_chatgpt",
                    "scope": "all_pending",
                    "include_expired": bool(options.get("include_expired", False)),
                    "include_previously_analyzed": bool(options.get("include_previously_analyzed", False)),
                    "shard_size": max(1, min(int(options.get("shard_size", 250)), 5000)),
                    "deep_analysis_batch_size": max(1, min(int(options.get("deep_analysis_batch_size", 25)), 250)),
                    "parallel_workers": max(1, min(int(options.get("parallel_workers", 4)), 16)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_START_INCREMENTAL__":
            result = await api(
                "POST",
                "procurement/analysis/runs/incremental/start/",
                json={
                    "trigger": "manual_chatgpt",
                    "scope": "all_pending",
                    "include_expired": bool(options.get("include_expired", False)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_STATUS__":
            run_id = str(options.get("run_id") or (source_record_ids[0] if source_record_ids else "")).strip()
            result = await api(
                "GET",
                f"procurement/analysis/runs/{run_id}/" if run_id else "procurement/analysis/runs/current/",
            )
        elif title == "__PDPONE_ANALYSIS_HISTORY__":
            result = await api(
                "GET",
                "procurement/analysis/runs/history/",
                params={"limit": max(1, min(int(options.get("limit", 25)), 100))},
            )
        elif title == "__PDPONE_ANALYSIS_CLAIM__":
            run_id = required_identifier("run_id")
            result = await api(
                "POST",
                f"procurement/analysis/runs/{run_id}/claim/",
                json={
                    "worker_id": str(options.get("worker_id", "chatgpt-compatibility-bridge"))[:120],
                    "limit": max(1, min(int(options.get("limit", 25)), 250)),
                    "lease_seconds": max(60, min(int(options.get("lease_seconds", 900)), 3600)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_DATASET_PREPARE__":
            run_id = required_identifier("run_id")
            result = await api(
                "POST",
                f"procurement/analysis/runs/{run_id}/datasets/prepare/",
                json={
                    "scope": str(options.get("scope", "all_pending")),
                    "shard_size": max(1, min(int(options.get("shard_size", 250)), 5000)),
                    "compression": str(options.get("compression", "gzip")),
                },
            )
        elif title == "__PDPONE_ANALYSIS_DATASET_STATUS__":
            dataset_id = required_identifier("dataset_id")
            result = await api("GET", f"procurement/analysis/datasets/{dataset_id}/")
        elif title == "__PDPONE_ANALYSIS_IMPORT__":
            run_id = required_identifier("run_id")
            results = options.get("results") or []
            if not isinstance(results, list):
                raise ValueError("results must be a JSON list.")
            canonical = json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload = {
                "results": results,
                "result_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "dry_run": bool(options.get("dry_run", False)),
            }
            if options.get("dataset_id"):
                payload["dataset_id"] = str(options["dataset_id"])
            result = await api("POST", f"procurement/analysis/runs/{run_id}/results/import/", json=payload)
        elif title == "__PDPONE_ANALYSIS_IMPORT_STATUS__":
            import_id = required_identifier("import_id")
            result = await api("GET", f"procurement/analysis/imports/{import_id}/")
        elif title == "__PDPONE_ANALYSIS_PAUSE__":
            run_id = required_identifier("run_id")
            result = await api("POST", f"procurement/analysis/runs/{run_id}/pause/", json={})
        elif title == "__PDPONE_ANALYSIS_RESUME__":
            run_id = required_identifier("run_id")
            result = await api("POST", f"procurement/analysis/runs/{run_id}/resume/", json={})
        else:
            raise ValueError("Unknown persistent analysis compatibility command.")
        return {
            "persistent_analysis": result,
            "compatibility_bridge": True,
            "requires_human_review": True,
            "draft_only": True,
        }

    payload = {
        "title": title,
        "summary": summary,
        "source_record_ids": source_record_ids,
        "model_label": "ChatGPT",
        "review_status": "ai_draft",
    }
    return {"report": await api("POST", "analysis-reports/", json=payload), "requires_human_review": True}


@mcp.tool(
    description="Return the local deployment agent and signed-queue status. This never changes the installation.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_deployment_status() -> dict:
    return get_queue_status()


@mcp.tool(
    description="Run signed PDP One disk maintenance after an explicit user request. It removes only unused Docker build cache, unused images, stopped containers, old verified backups beyond retention, and stale deployment staging. It never prunes Docker volumes.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
)
async def run_disk_maintenance(keep_local_final_backups: int = 2) -> dict:
    keep = int(keep_local_final_backups)
    if keep < 2 or keep > 10:
        raise ValueError("keep_local_final_backups must be between 2 and 10.")
    return enqueue("run_disk_maintenance", {"keep_local_final_backups": keep})


@mcp.tool(
    description="Return the active change-management workflow. While implementation is in progress, development-fast mode uses branch, CI, exact-commit deploy, short health and merge without routine approval, backup, restore verification, local snapshot or automatic rollback.",
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
        "code_snapshot_required": not fast,
        "restore_verification_required": not fast,
        "automatic_rollback_enabled": not fast,
        "approval_required": not fast,
        "heavy_preview_gate_required": not fast,
        "health_profile": "short" if fast else "layered",
        "emergency_recovery": (
            "redeploy_previous_commit_from_github"
            if fast
            else "verified_backup_and_code_snapshot"
        ),
        "production_changed": False,
        "requires_github_branch": True,
        "standard_mode_returns_when_trial_mode_is_disabled": True,
        "standard_mode_requires_explicit_implementation_completion": True,
    }


@mcp.tool(
    description="Return an exact-commit reference. In development-fast mode this is lightweight metadata only; the heavy Preview gate is reserved for standard mode.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def create_preview(commit_sha: str) -> dict:
    commit = validate_commit(commit_sha)
    fast = development_fast_mode()
    return {
        "commit_sha": commit,
        "production_changed": False,
        "mode": "development_fast" if fast else "standard",
        "gate": "standing-owner-authorization" if fast else "stop-for-explicit-user-approval",
        "preview_created_by": "GitHub/Sites workflow",
        "database_backup_required": not fast,
        "restore_verification_required": not fast,
        "code_snapshot_required": not fast,
        "automatic_rollback_enabled": not fast,
        "heavy_preview_gate_required": not fast,
    }


@mcp.tool(
    description="Record explicit approval for standard-mode deployment. Development-fast deployment uses standing owner authorization and does not require this per commit.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def request_deployment_approval(commit_sha: str, preview_id: str, approval_text: str) -> dict:
    commit = validate_commit(commit_sha)
    if approval_text.strip() not in {"تأیید است، Deploy کن", "تایید است، Deploy کن", "APPROVE DEPLOY"}:
        raise ValueError("The exact explicit deployment approval phrase was not supplied.")
    return enqueue(
        "approve_release",
        {
            "commit_sha": commit,
            "preview_id": validate_identifier(preview_id, "preview_id"),
            "approval_text": approval_text.strip(),
        },
    )


@mcp.tool(
    description="Create and isolate-restore-verify a final backup for standard mode or a commit explicitly marked as a destructive or sensitive database change.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def create_final_backup(commit_sha: str, deployment_id: str) -> dict:
    return enqueue(
        "create_final_backup",
        {
            "commit_sha": validate_commit(commit_sha),
            "deployment_id": validate_identifier(deployment_id, "deployment_id"),
        },
    )


@mcp.tool(
    description="Re-run integrity and isolated restore verification for a named backup used by standard mode or a sensitive database change.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def verify_backup_restore(backup_id: str) -> dict:
    return enqueue("verify_backup_restore", {"backup_id": backup_id})


async def _wait_for_agent_response(request_id: str, timeout_seconds: int = 900) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(30, min(int(timeout_seconds), 1500))
    while True:
        response = get_response(request_id)
        status = str(response.get("status", "pending"))
        if status != "pending":
            return response
        if loop.time() >= deadline:
            raise RuntimeError("Deployment Agent exact-commit reconciliation did not reach a terminal response before the bounded wait expired.")
        await asyncio.sleep(1)


@mcp.tool(
    description="Deploy one exact commit. Before deployment, the stable tool reconciles only the manifest-declared protected Windows Deployment Agent files to the same exact commit through the signed allowlisted Agent sync action. Development-fast mode then uses standing authorization; standard mode retains the full guarded deployment workflow.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
)
async def deploy_approved_release(commit_sha: str, deployment_id: str, preview_id: str) -> dict:
    commit = validate_commit(commit_sha)
    deployment = validate_identifier(deployment_id, "deployment_id")
    preview = validate_identifier(preview_id, "preview_id")
    queue_status = get_queue_status()
    if not queue_status.get("configured") or not queue_status.get("queue_available"):
        raise RuntimeError("The signed local Deployment Agent queue is not available.")
    if int(queue_status.get("pending_requests", 0)) != 0:
        raise RuntimeError("A signed Deployment Agent request is already pending. Refresh coordination before deployment.")

    sync_request = enqueue(
        "sync_agent_from_exact_commit",
        {"commit_sha": commit},
        ttl_seconds=1800,
    )
    sync_response = await _wait_for_agent_response(sync_request["request_id"])
    if str(sync_response.get("status", "")) != "succeeded":
        raise RuntimeError("Deployment Agent exact-commit reconciliation failed; the deployment request was not queued.")

    queue_status = get_queue_status()
    if int(queue_status.get("pending_requests", 0)) != 0:
        raise RuntimeError("Another signed Agent request appeared after reconciliation; deployment was not queued.")

    deployment_request = enqueue(
        "deploy_approved_release",
        {
            "commit_sha": commit,
            "deployment_id": deployment,
            "preview_id": preview,
        },
    )
    return {
        **deployment_request,
        "agent_reconciliation": {
            "request_id": sync_request["request_id"],
            "status": "succeeded",
            "exact_commit": commit,
            "fixed_action": "sync_agent_from_exact_commit",
        },
        "arbitrary_shell_allowed": False,
    }


@mcp.tool(
    description="Run post-deployment health. Development-fast mode uses a short health profile; standard mode may use the full layered profile.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def check_deployment_health(deployment_id: str = "") -> dict:
    normalized = validate_identifier(deployment_id, "deployment_id") if deployment_id else "current"
    return enqueue("check_deployment_health", {"deployment_id": normalized})


@mcp.tool(
    description="Run the standard-mode backup-and-snapshot rollback when explicitly requested. Development-fast recovery redeploys the previous GitHub commit instead.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
)
async def rollback_deployment(deployment_id: str, reason: str) -> dict:
    if not 1 <= len(reason.strip()) <= 500:
        raise ValueError("reason must be between 1 and 500 characters.")
    return enqueue(
        "rollback_deployment",
        {
            "deployment_id": validate_identifier(deployment_id, "deployment_id"),
            "reason": reason.strip(),
        },
    )


@mcp.tool(
    description="Return a local deployment-agent response by request ID.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
)
async def get_deployment_report(request_id: str) -> dict:
    return get_response(request_id)


@mcp.tool(
    description="Rotate the private MCP path token only after explicit confirmation. This temporarily disconnects the existing ChatGPT app and requires one URL update.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
)
async def rotate_mcp_token(confirmation: str) -> dict:
    if confirmation.strip() != "ROTATE MCP TOKEN":
        raise ValueError("Exact confirmation ROTATE MCP TOKEN is required.")
    return enqueue("rotate_mcp_token", {"confirmation": confirmation.strip()})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
