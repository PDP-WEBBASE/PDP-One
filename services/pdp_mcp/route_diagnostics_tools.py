from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
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


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record_external_reachability() -> dict[str, Any]:
    """Persist only proof that an external MCP diagnostic call reached this process.

    This is observability telemetry, not a recovery or runtime-control mutation.  It
    contains no token, URL, request content, user identity, or authorization data.
    """

    observed_at = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "schema": "pdp-one.mcp-external-observer.v1",
        "observed_at": observed_at,
        "status": "pass",
        "source": "connected_mcp_diagnostic_call",
        "secrets_included": False,
    }
    path = REPORT_ROOT / "external-observer.json"
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
        return payload
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            **payload,
            "status": "evidence_write_failed",
            "error_class": type(exc).__name__,
        }


def _incident_timeline(incident: dict[str, Any]) -> dict[str, Any]:
    started = _parse_timestamp(incident.get("started_at"))
    recovered = _parse_timestamp(incident.get("recovered_at"))
    if started is None:
        return {"timeline": [], "timeline_status": "incident_start_unavailable"}

    window_start = started - timedelta(minutes=15)
    window_end = (recovered or datetime.now(timezone.utc)) + timedelta(minutes=10)
    samples: list[dict[str, Any]] = []
    day = window_start.date()
    last_day = window_end.date()
    sample_root = REPORT_ROOT / "samples"

    while day <= last_day:
        path = sample_root / f"{day.isoformat()}.jsonl"
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            lines = []
        except OSError:
            lines = []
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            observed = _parse_timestamp(item.get("observed_at"))
            if observed is None or observed < window_start or observed > window_end:
                continue
            samples.append(item)
        day += timedelta(days=1)

    samples.sort(key=lambda item: str(item.get("observed_at", "")))
    if len(samples) > 90:
        samples = samples[-90:]
    return {
        "timeline": samples,
        "timeline_status": "available" if samples else "no_samples_in_window",
        "timeline_window": {
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "pre_incident_minutes": 15,
            "post_recovery_minutes": 10,
            "max_samples_returned": 90,
        },
    }


def register_route_diagnostics_tools(mcp: Any) -> None:
    @mcp.tool(
        description=(
            "Read the latest passive MCP route checkpoint summary and last incident metadata. "
            "A successful external call also records sanitized reachability evidence only; "
            "the tool never repairs, restarts, rotates tokens, or changes application/runtime state."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            openWorldHint=False,
            idempotentHint=True,
        ),
    )
    async def get_mcp_route_diagnostics() -> dict:
        external_observer = _record_external_reachability()
        result = _read_json(REPORT_ROOT / "latest.json")
        return {
            **result,
            "external_observer_current_call": external_observer,
            "diagnostic_only": True,
            "secrets_included": False,
        }

    @mcp.tool(
        description=(
            "Read one passive MCP route incident evidence bundle by incident ID, including the bounded local checkpoint timeline. "
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
        timeline = _incident_timeline(result) if result.get("incident_id") else {"timeline": [], "timeline_status": "incident_not_available"}
        return {
            **result,
            **timeline,
            "diagnostic_only": True,
            "secrets_included": False,
        }
