import os
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

API_URL = os.getenv("PDP_API_URL", "http://localhost:8000/api/v1").rstrip("/")
TOKEN = os.getenv("PDP_MCP_TOKEN", "")

mcp = FastMCP(
    "PDP One",
    instructions=(
        "Use read tools before write tools. Create contracts, receivables, payment receipts, and analyses only as drafts. "
        "Never claim a draft is approved or financially final. Use returned record IDs in follow-up calls."
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
            raise RuntimeError(f"PDP One API request failed with HTTP {exc.response.status_code}.") from exc
        return response.json()

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
async def create_contract_draft(code: str, title: str, employer: str, field: str = "", value_rials: int | None = None, due_date: str | None = None) -> dict:
    payload = {"code": code, "title": title, "employer": employer, "field": field, "value_rials": value_rials, "due_date": due_date, "progress": 0, "status": "draft"}
    return {"draft": await api("POST", "contracts/", json=payload), "requires_human_review": True}


@mcp.tool(
    description="Use this when the user explicitly asks to register a receivable or statement in PDP One. It always creates a finance draft for human review.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def create_receivable_draft(contract_code: str, contract_title: str, employer: str, statement_title: str, amount_rials: int, due_date: str, received_rials: int = 0) -> dict:
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
async def create_payment_receipt_draft(receivable_id: str, amount_rials: int, received_date: str, tracking_code: str = "", note: str = "") -> dict:
    payload = {
        "receivable": receivable_id,
        "amount_rials": amount_rials,
        "received_date": received_date,
        "tracking_code": tracking_code,
        "note": note,
    }
    return {"draft": await api("POST", "payment-receipts/", json=payload), "requires_human_review": True}

@mcp.tool(
    description="Use this when the user explicitly asks to save a ChatGPT analysis in PDP One. The result is stored as an AI draft, never as an approved report.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
)
async def save_analysis_draft(title: str, summary: str, source_record_ids: list[str]) -> dict:
    payload = {"title": title, "summary": summary, "source_record_ids": source_record_ids, "model_label": "ChatGPT", "review_status": "ai_draft"}
    return {"report": await api("POST", "analysis-reports/", json=payload), "requires_human_review": True}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
