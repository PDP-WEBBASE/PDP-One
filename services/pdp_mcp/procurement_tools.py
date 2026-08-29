from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ApiCallable = Callable[..., Awaitable[Any]]


def register_procurement_tools(mcp: FastMCP, api: ApiCallable) -> None:
    @mcp.tool(
        description=(
            "Read the lightweight active PDP One analysis-context manifest. "
            "Call this first for every scheduled or manual PDP analysis run."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_analysis_context_manifest(known_version: int | None = None) -> dict:
        params = {}
        if known_version is not None:
            params["known_version"] = known_version
        return await api("GET", "procurement/analysis/context/manifest/", params=params)

    @mcp.tool(
        description=(
            "Read the full active PDP One analysis snapshot only when the manifest reports a changed version. "
            "It contains the current role, prompts, company profile, qualifications, keywords, and experience summary."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_analysis_context_snapshot() -> dict:
        return await api("GET", "procurement/analysis/context/active/")

    @mcp.tool(
        description="Return the latest completed PDP One extraction run and its new or changed record counts.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_latest_procurement_extraction() -> dict:
        return await api("GET", "procurement/analysis/latest-extraction/")

    @mcp.tool(
        description=(
            "Read one completed or active procurement extraction run with its persisted page and error detail. "
            "Use this for governed acceptance evidence without starting or changing an extraction."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_extraction_run_detail(run_id: str) -> dict:
        return await api("GET", f"procurement/extraction-runs/{run_id}/")

    @mcp.tool(
        description=(
            "List PDP One tender and inquiry records that still need analysis for the active context and current content hash. "
            "Use batches of at most 50 records."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def list_unanalyzed_procurement_notices(limit: int = 20) -> dict:
        return await api("GET", "procurement/analysis/queue/", params={"limit": min(max(limit, 1), 50)})

    @mcp.tool(
        description=(
            "Run a full read-only Zero-Loss reconciliation across every visible procurement notice. "
            "Reports active-context/current-content analysis coverage, orphan work, stale run items, explicit poison/failed exceptions, "
            "and analysis_orphan_count. It does not mutate procurement data."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_analysis_integrity() -> dict:
        return await api("GET", "procurement/analysis/integrity/")

    @mcp.tool(
        description=(
            "Repair Zero-Loss analysis integrity for the existing active run. Missing current-basis notices are attached as pending work; "
            "stale or terminal-without-valid-result items are reset only when they are not under a live lease. Historical AI drafts are preserved. "
            "This never approves or publishes a procurement decision."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def repair_procurement_analysis_integrity() -> dict:
        return await api("POST", "procurement/analysis/integrity/repair/", json={})

    @mcp.tool(
        description=(
            "Read one procurement notice with its normalized source data, current analysis basis hash, and latest draft analysis."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_notice_analysis_context(notice_id: str) -> dict:
        return await api("GET", f"procurement/analysis/notices/{notice_id}/context/")

    @mcp.tool(
        description=(
            "Start a PDP analysis request after the latest extraction. Use trigger manual_chatgpt for the one-word PDP command "
            "or scheduled for the recurring task. This only opens a draft workflow."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def start_pdp_analysis_request(trigger: str = "manual_chatgpt", extraction_run_id: str = "") -> dict:
        if trigger not in {"manual_chatgpt", "scheduled"}:
            raise ValueError("trigger must be manual_chatgpt or scheduled")
        payload: dict[str, Any] = {"trigger": trigger}
        if extraction_run_id:
            payload["extraction_run"] = extraction_run_id
        result = await api("POST", "procurement/analysis-requests/", json=payload)
        return {"analysis_request": result, "command": "PDP", "draft_workflow": True}

    @mcp.tool(
        description="Open one analysis batch for an existing PDP analysis request.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def create_pdp_analysis_batch(request_id: str, item_count: int) -> dict:
        if not 0 <= item_count <= 50:
            raise ValueError("item_count must be between 0 and 50")
        return await api(
            "POST",
            "procurement/analysis-batches/",
            json={"request": request_id, "item_count": item_count},
        )

    @mcp.tool(
        description=(
            "Save one structured ChatGPT tender or inquiry recommendation as a PDP One AI draft. "
            "This does not select the notice, approve participation, submit a proposal, or make a final company decision."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def create_notice_analysis_draft(
        notice_id: str,
        batch_id: str,
        is_recommended: bool,
        score: int,
        priority: str,
        fit_for_pdp: str,
        reason: str,
        recommended_action: str,
        category: str = "",
        matched_experience: list[dict] | None = None,
        risk_notes: list[str] | None = None,
        confidence: float = 0,
        raw_output: dict | None = None,
    ) -> dict:
        if priority not in {"low", "medium", "high", "urgent"}:
            raise ValueError("priority must be low, medium, high, or urgent")
        if not 0 <= score <= 100 or not 0 <= confidence <= 100:
            raise ValueError("score and confidence must be between 0 and 100")
        payload = {
            "notice": notice_id,
            "batch": batch_id,
            "is_recommended": is_recommended,
            "score": score,
            "priority": priority,
            "fit_for_pdp": fit_for_pdp,
            "category": category,
            "reason": reason,
            "recommended_action": recommended_action,
            "matched_experience": matched_experience or [],
            "risk_notes": risk_notes or [],
            "confidence": confidence,
            "raw_output": raw_output or {},
        }
        return {
            "draft": await api("POST", "procurement/analysis-drafts/", json=payload),
            "requires_human_review": True,
            "final_company_decision": False,
        }

    @mcp.tool(
        description="Complete an analysis batch and store only its processing summary.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def complete_pdp_analysis_batch(
        batch_id: str,
        completed_count: int,
        failed_count: int = 0,
        summary: dict | None = None,
    ) -> dict:
        return await api(
            "POST",
            f"procurement/analysis-batches/{batch_id}/complete/",
            json={
                "completed_count": max(0, completed_count),
                "failed_count": max(0, failed_count),
                "summary": summary or {},
            },
        )

    @mcp.tool(
        description=(
            "Complete a PDP analysis request as completed, no_changes, or failed. "
            "This records workflow status and never approves a tender decision."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def complete_pdp_analysis_request(
        request_id: str,
        status: str = "completed",
        last_error: str = "",
        metadata: dict | None = None,
    ) -> dict:
        if status not in {"completed", "no_changes", "failed"}:
            raise ValueError("status must be completed, no_changes, or failed")
        return await api(
            "POST",
            f"procurement/analysis-requests/{request_id}/complete/",
            json={"status": status, "last_error": last_error, "metadata": metadata or {}},
        )
