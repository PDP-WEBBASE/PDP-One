from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


@dataclass
class RouteProbeResult:
    status: str
    checks: dict[str, str] = field(default_factory=dict)
    detail: str = ""


async def _run_check(
    adapter: Callable[[], Awaitable[str]] | None,
    fallback: str,
) -> str:
    if adapter is None:
        return fallback
    return await adapter()


async def probe_mcp_route_chain(
    *,
    public_route_check: Callable[[], Awaitable[str]] | None = None,
    token_route_check: Callable[[], Awaitable[str]] | None = None,
    nginx_check: Callable[[], Awaitable[str]] | None = None,
    container_check: Callable[[], Awaitable[str]] | None = None,
    handshake_check: Callable[[], Awaitable[str]] | None = None,
) -> RouteProbeResult:
    """Non-destructive MCP route diagnostics.

    Runtime adapters are injected by the execution environment. This module
    does not restart services, rotate credentials, create sessions, or mutate
    runtime state.
    """
    checks = {
        "public_route": await _run_check(public_route_check, "unknown"),
        "token_route": await _run_check(token_route_check, "unknown"),
        "nginx_endpoint": await _run_check(nginx_check, "unknown"),
        "mcp_container": await _run_check(container_check, "unknown"),
        "session_handshake": await _run_check(handshake_check, "not_attempted"),
    }

    if "failed" in checks.values():
        status = "failed"
    elif all(value == "healthy" for value in checks.values()):
        status = "healthy"
    else:
        status = "partial"

    return RouteProbeResult(
        status=status,
        checks=checks,
        detail="Runtime-specific adapters determine actual route health.",
    )


def heartbeat_snapshot() -> dict[str, Any]:
    return {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "creates_session": False,
        "database_access": False,
    }
