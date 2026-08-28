"""Backward-compatible sanitized Public Edge status for the stable deployment-status tool."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPORT_ROOT = Path("/deployment-agent/reports")
OBSERVER_LATEST = REPORT_ROOT / "mcp-route-observability" / "latest.json"
EDGE_WATCHDOG = REPORT_ROOT / "public-edge-watchdog.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _age_seconds(value: Any) -> int | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0, int((_utcnow() - parsed.astimezone(timezone.utc)).total_seconds()))


def _observer_summary() -> dict[str, Any]:
    unavailable = {
        "available": False,
        "observed_at": None,
        "age_seconds": None,
        "stale": True,
        "overall": "unknown",
        "active_incident": None,
        "last_incident": None,
        "consecutive_failures": 0,
        "consecutive_successes": 0,
        "first_failed_checkpoint": None,
        "root_cause_classification": "unknown",
        "root_cause_confidence": "unknown",
        "external_correlation_required": False,
        "passive_only": True,
        "repair_actions": 0,
        "secrets_included": False,
    }
    raw = _read_json(OBSERVER_LATEST)
    if raw is None or str(raw.get("schema", "")) != "pdp-one.mcp-route-observability.v2":
        return unavailable
    age = _age_seconds(raw.get("observed_at"))
    return {
        "available": True,
        "observed_at": str(raw.get("observed_at") or "")[:64] or None,
        "age_seconds": age,
        "stale": age is None or age > 180,
        "overall": str(raw.get("overall", "unknown"))[:32],
        "active_incident": str(raw.get("active_incident") or "")[:64] or None,
        "last_incident": str(raw.get("last_incident") or "")[:64] or None,
        "consecutive_failures": max(0, int(raw.get("consecutive_failures", 0))),
        "consecutive_successes": max(0, int(raw.get("consecutive_successes", 0))),
        "first_failed_checkpoint": str(raw.get("first_failed_checkpoint") or "")[:16] or None,
        "root_cause_classification": str(raw.get("root_cause_classification", "unknown"))[:64],
        "root_cause_confidence": str(raw.get("root_cause_confidence", "unknown"))[:64],
        "external_correlation_required": bool(raw.get("external_correlation_required", False)),
        "passive_only": bool(raw.get("passive_only", True)),
        "repair_actions": max(0, int(raw.get("repair_actions", 0))),
        "secrets_included": bool(raw.get("secrets_included", False)),
    }


def _watchdog_summary() -> dict[str, Any]:
    unavailable = {
        "available": False,
        "checked_at": None,
        "age_seconds": None,
        "stale": True,
        "status": "unknown",
        "active_incident": None,
        "repair_attempted": False,
        "repair_stage": "none",
        "repair_actions": 0,
        "repair_suppressed_deployment": False,
        "cooldown_seconds_remaining": 0,
        "final_public_mcp": "unknown",
        "stable_status_refreshed": False,
        "secrets_included": False,
        "token_rotated": False,
        "tailscale_identity_reset": False,
        "database_changed": False,
        "docker_volumes_touched": False,
    }
    raw = _read_json(EDGE_WATCHDOG)
    if raw is None or str(raw.get("schema", "")) != "pdp-one.public-edge-watchdog.v1":
        return unavailable
    age = _age_seconds(raw.get("checked_at"))
    return {
        "available": True,
        "checked_at": str(raw.get("checked_at") or "")[:64] or None,
        "age_seconds": age,
        "stale": age is None or age > 180,
        "status": str(raw.get("status", "unknown"))[:96],
        "active_incident": str(raw.get("active_incident") or "")[:64] or None,
        "repair_attempted": bool(raw.get("repair_attempted", False)),
        "repair_stage": str(raw.get("repair_stage", "none"))[:64],
        "repair_actions": max(0, int(raw.get("repair_actions", 0))),
        "repair_suppressed_deployment": bool(raw.get("repair_suppressed_deployment", False)),
        "cooldown_seconds_remaining": max(0, int(raw.get("cooldown_seconds_remaining", 0))),
        "final_public_mcp": str(raw.get("final_public_mcp", "unknown"))[:32],
        "stable_status_refreshed": bool(raw.get("stable_status_refreshed", False)),
        "secrets_included": bool(raw.get("secrets_included", False)),
        "token_rotated": bool(raw.get("token_rotated", False)),
        "tailscale_identity_reset": bool(raw.get("tailscale_identity_reset", False)),
        "database_changed": bool(raw.get("database_changed", False)),
        "docker_volumes_touched": bool(raw.get("docker_volumes_touched", False)),
    }


def wrap_get_queue_status(base_get_queue_status: Callable[[], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
    """Return the existing status plus additive, sanitized V3 diagnostics."""

    def enhanced() -> dict[str, Any]:
        base = base_get_queue_status()
        return {
            **base,
            "mcp_route_observer": _observer_summary(),
            "public_edge_watchdog": _watchdog_summary(),
        }

    return enhanced
