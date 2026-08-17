from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from mcp.types import ToolAnnotations

ApiCall = Callable[..., Awaitable[Any]]


def register_procurement_analysis_tools(mcp, api: ApiCall) -> None:
    @mcp.tool(
        description="Start or continue one full pending procurement analysis run. It discovers all currently eligible notices and is not limited to one batch.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def start_full_pending_analysis(
        include_expired: bool = False,
        include_previously_analyzed: bool = False,
        shard_size: int = 250,
        deep_analysis_batch_size: int = 25,
        parallel_workers: int = 4,
    ) -> dict:
        return await api(
            "POST",
            "procurement/analysis/runs/full-pending/start/",
            json={
                "trigger": "manual_chatgpt",
                "scope": "all_pending",
                "include_expired": bool(include_expired),
                "include_previously_analyzed": bool(include_previously_analyzed),
                "shard_size": max(1, min(int(shard_size), 5000)),
                "deep_analysis_batch_size": max(1, min(int(deep_analysis_batch_size), 250)),
                "parallel_workers": max(1, min(int(parallel_workers), 16)),
            },
        )

    @mcp.tool(
        description="Start or continue the incremental procurement analysis run used by the scheduled workflow.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def start_incremental_analysis(include_expired: bool = False) -> dict:
        return await api(
            "POST",
            "procurement/analysis/runs/incremental/start/",
            json={"trigger": "manual_chatgpt", "scope": "all_pending", "include_expired": bool(include_expired)},
        )

    @mcp.tool(
        description="Return exact queue counters, the active Context and the active persistent analysis run.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_analysis_run_status(run_id: str = "") -> dict:
        if run_id:
            return await api("GET", f"procurement/analysis/runs/{run_id}/")
        return await api("GET", "procurement/analysis/runs/current/")

    @mcp.tool(
        description="List recent full-pending and incremental procurement analysis runs and their persisted checkpoints.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_analysis_run_history(limit: int = 25) -> dict:
        return await api("GET", "procurement/analysis/runs/history/", params={"limit": max(1, min(int(limit), 100))})

    @mcp.tool(
        description="Pause future work for a persistent procurement analysis run without deleting any completed AI drafts.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def pause_procurement_analysis_run(run_id: str) -> dict:
        return await api("POST", f"procurement/analysis/runs/{run_id}/pause/", json={})

    @mcp.tool(
        description="Resume a paused procurement analysis run from its persisted PostgreSQL checkpoint.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def resume_procurement_analysis_run(run_id: str) -> dict:
        return await api("POST", f"procurement/analysis/runs/{run_id}/resume/", json={})

    @mcp.tool(
        description="Cancel only future processing for a procurement analysis run. Healthy imported AI drafts remain intact.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False, idempotentHint=False),
    )
    async def cancel_procurement_analysis_run(run_id: str) -> dict:
        return await api("POST", f"procurement/analysis/runs/{run_id}/cancel/", json={})

    @mcp.tool(
        description="Claim a compact direct-ChatGPT work package. The response carries Context once per batch, omits empty notice fields, supports up to 500 records, and includes a short-key schema for safe import.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def claim_procurement_analysis_work(
        run_id: str,
        worker_id: str = "chatgpt-connected-app",
        limit: int = 500,
        lease_seconds: int = 3600,
    ) -> dict:
        return await api(
            "POST",
            f"procurement/analysis/runs/{run_id}/claim/",
            json={
                "worker_id": worker_id[:120],
                "limit": max(1, min(int(limit), 500)),
                "lease_seconds": max(60, min(int(lease_seconds), 3600)),
            },
        )

    @mcp.tool(
        description="Prepare the official Procurement SQL, sharded JSONL, CSV and Manifest dataset for a persistent analysis run.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def prepare_procurement_analysis_dataset(
        run_id: str,
        scope: str = "all_pending",
        shard_size: int = 250,
        compression: str = "gzip",
    ) -> dict:
        return await api(
            "POST",
            f"procurement/analysis/runs/{run_id}/datasets/prepare/",
            json={"scope": scope, "shard_size": max(1, min(int(shard_size), 5000)), "compression": compression},
        )

    @mcp.tool(
        description="Return dataset generation progress, exact files, sizes, SHA-256 values and SQL restore validation.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_analysis_dataset_status(dataset_id: str) -> dict:
        return await api("GET", f"procurement/analysis/datasets/{dataset_id}/")

    @mcp.tool(
        description="Return the verified download locations for one ready Procurement analysis dataset. Large file contents are not embedded in JSON.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def download_procurement_analysis_dataset(dataset_id: str) -> dict:
        result = await api("GET", f"procurement/analysis/datasets/{dataset_id}/")
        dataset = result.get("dataset", result)
        files = []
        for item in dataset.get("files", []):
            name = str(item.get("name", ""))
            files.append({
                **item,
                "download_path": f"procurement/analysis/datasets/{dataset_id}/download/{name}/",
            })
        return {"dataset_id": dataset_id, "status": dataset.get("status"), "files": files}

    @mcp.tool(
        description="Import validated structured results into one run. It only creates AI drafts, validates Notice/Content/Context/Claim hashes and never publishes or creates financial records.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def import_procurement_analysis_results(
        run_id: str,
        results: list[dict[str, Any]],
        dataset_id: str = "",
        dry_run: bool = False,
    ) -> dict:
        canonical = json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        payload: dict[str, Any] = {
            "results": results,
            "result_hash": digest,
            "dry_run": bool(dry_run),
        }
        if dataset_id:
            payload["dataset_id"] = dataset_id
        return await api("POST", f"procurement/analysis/runs/{run_id}/results/import/", json=payload)

    @mcp.tool(
        description="Return exact imported, duplicate, rejected, invalid hash/context, error, remaining and checkpoint counts for one result import.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_analysis_import_status(import_id: str) -> dict:
        return await api("GET", f"procurement/analysis/imports/{import_id}/")
