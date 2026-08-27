from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

REPORT_ROOT = Path(
    os.getenv(
        "PDP_MCP_ROUTE_OBSERVABILITY_REPORTS",
        "/deployment-agent/reports/mcp-route-observability",
    )
)
_INCIDENT_ID = re.compile(r"^MCP-INC-[0-9]{8}-[0-9]{4}$")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "not_available", "path": path.name}
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "unreadable",
            "path": path.name,
            "error_class": type(exc).__name__,
        }
    if not isinstance(payload, dict):
        return {"status": "invalid", "path": path.name}
    return payload


def register_route_diagnostics_tools(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Read the latest passive MCP route checkpoint summary and last incident metadata. "
            "This is diagnostic-only and never repairs, restarts, rotates tokens, or changes runtime state."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            openWorldHint=False,
            idempotentHint=True,
        ),
    )
    async def get_mcp_route_diagnostics() -> dict:
        result = _read_json(REPORT_ROOT / "latest.json")
        return {
            **result,
            "diagnostic_only": True,
            "secrets_included": False,
        }

    @mcp.tool(
        description=(
            "Read one passive MCP route incident evidence bundle by incident ID. "
            "Evidence is non-sensitive and the tool never performs recovery actions."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            openWorldHint=False,
            idempotentHint=True,
        ),
    )
    async def get_mcp_incident_report(incident_id: str) -> dict:
        value = str(incident_id or "").strip()
        if not _INCIDENT_ID.fullmatch(value):
            raise ValueError("incident_id must match MCP-INC-YYYYMMDD-NNNN")
        result = _read_json(REPORT_ROOT / "incidents" / f"{value}.json")
        return {
            **result,
            "diagnostic_only": True,
            "secrets_included": False,
        }
