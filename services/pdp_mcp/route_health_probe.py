from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RouteProbeResult:
    status: str
    checks: dict[str, str] = field(default_factory=dict)
    detail: str = ""


async def probe_mcp_route_chain() -> RouteProbeResult:
    """Non-destructive MCP route diagnostics.

    This module intentionally does not restart services, rotate credentials,
    create sessions, or mutate runtime state. It is a diagnostics boundary
    used before any repair decision.
    """
    return RouteProbeResult(
        status="not_configured",
        checks={
            "public_route": "unknown",
            "token_route": "unknown",
            "nginx_endpoint": "unknown",
            "mcp_container": "unknown",
            "session_handshake": "not_attempted",
        },
        detail="Probe adapters require runtime-specific wiring.",
    )


def heartbeat_snapshot() -> dict[str, Any]:
    return {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "creates_session": False,
        "database_access": False,
    }
