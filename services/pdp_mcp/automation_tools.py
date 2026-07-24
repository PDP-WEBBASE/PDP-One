from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ApiCallable = Callable[..., Awaitable[Any]]


def register_automation_tools(mcp: FastMCP, api: ApiCallable) -> None:
    @mcp.tool(
        description=(
            "Read the central PDP One procurement automation settings, including extraction cadence, next extraction time, "
            "analysis delay, enabled source behavior, and the manual command PDP."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_automation_settings() -> dict:
        result = await api("GET", "procurement/automation-settings/")
        items = result.get("results", result) if isinstance(result, dict) else result
        if isinstance(items, list):
            return items[0] if items else {"configured": False}
        return items
