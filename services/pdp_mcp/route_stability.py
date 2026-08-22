from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RouteState:
    """Non-sensitive MCP route diagnostics only."""

    last_success: str | None = None
    last_failure: str | None = None
    consecutive_failures: int = 0
    last_repair_action: str | None = None
    last_repair_result: str | None = None


class RouteStabilityController:
    """Bounded MCP route recovery decision helper.

    This intentionally does not store tokens, URLs, credentials, or runtime secrets.
    """

    def __init__(self) -> None:
        self.state = RouteState()

    def record_success(self) -> None:
        self.state.last_success = datetime.now(timezone.utc).isoformat()
        self.state.consecutive_failures = 0

    def record_failure(self) -> int:
        self.state.last_failure = datetime.now(timezone.utc).isoformat()
        self.state.consecutive_failures += 1
        return self.state.consecutive_failures

    def next_action(self) -> str:
        if self.state.consecutive_failures <= 1:
            return "retry_verify"
        if self.state.consecutive_failures < 3:
            return "bounded_route_refresh"
        return "persistent_route_repair_review"

    def snapshot(self) -> dict:
        return {
            "last_success": self.state.last_success,
            "last_failure": self.state.last_failure,
            "consecutive_failures": self.state.consecutive_failures,
            "last_repair_action": self.state.last_repair_action,
            "last_repair_result": self.state.last_repair_result,
        }
