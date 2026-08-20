"""Narrow, signed queue used by PDP One's local Windows deployment agent.

The MCP container can request only enum actions. It cannot pass shell text.
The Windows agent independently verifies the HMAC, expiry, nonce and action.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

QUEUE_ROOT = Path(os.getenv("PDP_DEPLOYMENT_QUEUE", "/deployment-agent/queue"))
REPORT_ROOT = Path(os.getenv("PDP_DEPLOYMENT_REPORTS", "/deployment-agent/reports"))
SIGNING_KEY = os.getenv("PDP_DEPLOYMENT_AGENT_SIGNING_KEY", "")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = 1800
ACTION_TTL_SECONDS = {
    # Layered health, exact Agent synchronization and composite promotion can
    # wait behind Windows startup, Agent restart, and public-route retries.
    "check_deployment_health": 1800,
    "promote_exact_candidate": 1800,
    "sync_agent_from_exact_commit": 1800,
    "repair_pdp_one_connectivity": 1800,
}
ALLOWED_ACTIONS = {
    "approve_release",
    "create_final_backup",
    "verify_backup_restore",
    "deploy_approved_release",
    "promote_exact_candidate",
    "sync_agent_from_exact_commit",
    "ensure_pdp_one_started",
    "repair_pdp_one_connectivity",
    "collect_pdp_one_diagnostics",
    "check_deployment_health",
    "run_disk_maintenance",
    "rollback_deployment",
    "rotate_mcp_token",
}
EMERGENCY_RESERVE_BYTES = max(1024 * 1024, int(os.getenv("PDP_QUEUE_RESERVE_BYTES", str(8 * 1024 * 1024))))
LOW_SPACE_BYTES = max(512 * 1024, int(os.getenv("PDP_QUEUE_LOW_SPACE_BYTES", str(2 * 1024 * 1024))))
RESERVE_PATH = QUEUE_ROOT / ".queue-emergency-reserve"
_SAFE_REPORT_FIELDS = (
    "schema",
    "deployment_id",
    "preview_id",
    "approved_commit",
    "previous_commit",
    "started_at",
    "completed_at",
    "status",
    "stage",
    "change_management_mode",
    "image_source",
    "image_mode",
    "local_image_build_performed",
    "production_changed",
    "health_profile",
    "changed_services",
    "changed_paths",
    "active_images",
    "retained_previous_images",
    "connectivity_repair_attempted",
    "connectivity_repair_succeeded",
    "error",
)
_SECRET_TEXT_RE = re.compile(
    r"(?i)(?:bearer\s+\S+|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+|authorization\s*[:=]\s*\S+)"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _disk_free_bytes() -> int:
    # This is intentionally the signed-queue filesystem safety metric. It is
    # not advertised as Windows C: capacity; Windows-side Disk Guard reports
    # remain authoritative for host C: free-space decisions.
    probe = QUEUE_ROOT if QUEUE_ROOT.exists() else QUEUE_ROOT.parent
    try:
        return int(shutil.disk_usage(probe).free)
    except OSError:
        return -1


def _release_emergency_reserve_if_needed() -> bool:
    free_bytes = _disk_free_bytes()
    if free_bytes >= 0 and free_bytes < LOW_SPACE_BYTES and RESERVE_PATH.exists():
        RESERVE_PATH.unlink(missing_ok=True)
        return True
    return False


def _ensure_emergency_reserve() -> None:
    if RESERVE_PATH.exists():
        return
    free_bytes = _disk_free_bytes()
    if free_bytes < EMERGENCY_RESERVE_BYTES * 4:
        return
    RESERVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    chunk = b"\0" * min(1024 * 1024, EMERGENCY_RESERVE_BYTES)
    remaining = EMERGENCY_RESERVE_BYTES
    temporary = RESERVE_PATH.with_suffix(".tmp")
    try:
        with temporary.open("wb") as handle:
            while remaining > 0:
                part = chunk if remaining >= len(chunk) else chunk[:remaining]
                handle.write(part)
                remaining -= len(part)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, RESERVE_PATH)
    except OSError:
        temporary.unlink(missing_ok=True)


def _require_queue() -> None:
    if len(SIGNING_KEY) < 32:
        raise RuntimeError("The local deployment agent signing key is not configured.")
    for name in ("incoming", "responses"):
        (QUEUE_ROOT / name).mkdir(parents=True, exist_ok=True)
    _ensure_emergency_reserve()


def validate_commit(commit_sha: str) -> str:
    value = commit_sha.strip().lower()
    if not COMMIT_RE.fullmatch(value):
        raise ValueError("commit_sha must be an exact 40-character Git commit SHA.")
    return value


def validate_identifier(value: str, field: str) -> str:
    normalized = value.strip()
    if not IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(f"{field} must be a safe 1-64 character identifier.")
    return normalized


def _validated_rejected_deployment_id(request_id: str) -> str | None:
    rejected = QUEUE_ROOT / "rejected" / f"{request_id}.json"
    if not rejected.exists():
        return None
    try:
        envelope = json.loads(rejected.read_text(encoding="utf-8-sig"))
        payload_bytes = base64.b64decode(str(envelope.get("payload_b64", "")), validate=True)
        signature = str(envelope.get("signature", ""))
        expected = hmac.new(SIGNING_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        if str(payload.get("request_id", "")) != request_id:
            return None
        if str(payload.get("action", "")) not in {"deploy_approved_release", "promote_exact_candidate"}:
            return None
        params = payload.get("params")
        if not isinstance(params, dict):
            return None
        return validate_identifier(str(params.get("deployment_id", "")), "deployment_id")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _sanitize_report_value(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_TEXT_RE.sub("[REDACTED]", value)[:4000]
    if isinstance(value, list):
        return [_sanitize_report_value(item) for item in value[:500]]
    if isinstance(value, dict):
        return {str(key)[:128]: _sanitize_report_value(item) for key, item in list(value.items())[:200]}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1000]


def _read_sanitized_deployment_report(deployment_id: str) -> dict[str, Any] | None:
    normalized = validate_identifier(deployment_id, "deployment_id")
    report_path = REPORT_ROOT / f"{normalized}.json"
    if not report_path.exists() or not report_path.is_file():
        return None
    try:
        with report_path.open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict) or str(raw.get("deployment_id", "")) != normalized:
        return None
    return {
        key: _sanitize_report_value(raw[key])
        for key in _SAFE_REPORT_FIELDS
        if key in raw
    }


def _read_agent_watchdog_status() -> dict[str, Any]:
    report_path = REPORT_ROOT / "deployment-agent-watchdog.json"
    unavailable = {
        "available": False,
        "status": "unknown",
        "checked_at": None,
        "age_seconds": None,
        "stale": True,
        "task_state_after": "unknown",
        "incoming_requests": None,
    }
    if not report_path.exists() or not report_path.is_file():
        return unavailable
    try:
        with report_path.open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict) or str(raw.get("schema", "")) != "pdp-one.deployment-agent-watchdog.v1":
            return unavailable
        checked_at_text = str(raw.get("checked_at", ""))
        checked_at = datetime.fromisoformat(checked_at_text.replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age = max(0, int((_utcnow() - checked_at.astimezone(timezone.utc)).total_seconds()))
        return {
            "available": True,
            "status": str(raw.get("status", "unknown"))[:64],
            "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
            "age_seconds": age,
            "stale": age > 180,
            "task_state_after": str(raw.get("task_state_after", "unknown"))[:64],
            "task_recreated": bool(raw.get("task_recreated", False)),
            "task_enabled": bool(raw.get("task_enabled", False)),
            "start_requested": bool(raw.get("start_requested", False)),
            "incoming_requests": int(raw.get("incoming_requests", 0)),
            "error": _sanitize_report_value(raw.get("error")),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return unavailable


def _read_public_mcp_connectivity_status() -> dict[str, Any]:
    report_path = REPORT_ROOT / "public-mcp-connectivity.json"
    unavailable = {
        "available": False,
        "status": "unknown",
        "checked_at": None,
        "age_seconds": None,
        "stale": True,
        "local_mcp": "unknown",
        "public_web": "unknown",
        "public_api": "unknown",
        "public_mcp": "unknown",
        "dns_state": "unknown",
        "consecutive_mcp_only_failures": 0,
        "last_funnel_repair_at": None,
        "last_funnel_repair_result": "unknown",
        "cooldown_seconds_remaining": 0,
        "repair_suppressed_deployment": False,
        "confirmation_count": 0,
    }
    if not report_path.exists() or not report_path.is_file():
        return unavailable
    try:
        with report_path.open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict) or str(raw.get("schema", "")) != "pdp-one.public-mcp-connectivity.v1":
            return unavailable
        checked_at_text = str(raw.get("checked_at", ""))
        checked_at = datetime.fromisoformat(checked_at_text.replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age = max(0, int((_utcnow() - checked_at.astimezone(timezone.utc)).total_seconds()))
        return {
            "available": True,
            "status": str(raw.get("status", "unknown"))[:64],
            "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
            "age_seconds": age,
            "stale": age > 900,
            "local_mcp": str(raw.get("local_mcp", "unknown"))[:32],
            "public_web": str(raw.get("public_web", "unknown"))[:32],
            "public_api": str(raw.get("public_api", "unknown"))[:32],
            "public_mcp": str(raw.get("public_mcp", "unknown"))[:32],
            "dns_state": str(raw.get("dns_state", "unknown"))[:64],
            "consecutive_mcp_only_failures": max(0, int(raw.get("consecutive_mcp_only_failures", 0))),
            "last_funnel_repair_at": _sanitize_report_value(raw.get("last_funnel_repair_at")),
            "last_funnel_repair_result": str(raw.get("last_funnel_repair_result", "unknown"))[:64],
            "cooldown_seconds_remaining": max(0, int(raw.get("cooldown_seconds_remaining", 0))),
            "repair_suppressed_deployment": bool(raw.get("repair_suppressed_deployment", False)),
            "confirmation_count": max(0, int(raw.get("confirmation_count", 0))),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return unavailable


def _pending_request_diagnostics(incoming: Path) -> dict[str, Any]:
    result = {
        "expired_signed_requests": 0,
        "oldest_pending_age_seconds": None,
    }
    if not incoming.exists() or len(SIGNING_KEY) < 32:
        return result
    now = _utcnow()
    oldest_age: int | None = None
    expired = 0
    for path in list(incoming.glob("*.json"))[:200]:
        try:
            envelope = json.loads(path.read_text(encoding="utf-8-sig"))
            payload_bytes = base64.b64decode(str(envelope.get("payload_b64", "")), validate=True)
            signature = str(envelope.get("signature", ""))
            expected = hmac.new(SIGNING_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                continue
            payload = json.loads(payload_bytes.decode("utf-8"))
            created = datetime.fromisoformat(str(payload.get("created_at", "")).replace("Z", "+00:00"))
            expires = datetime.fromisoformat(str(payload.get("expires_at", "")).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            age = max(0, int((now - created.astimezone(timezone.utc)).total_seconds()))
            oldest_age = age if oldest_age is None else max(oldest_age, age)
            if expires.astimezone(timezone.utc) <= now:
                expired += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    result["expired_signed_requests"] = expired
    result["oldest_pending_age_seconds"] = oldest_age
    return result


def enqueue(
    action: str,
    params: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported deployment-agent action.")
    reserve_released = _release_emergency_reserve_if_needed()
    _require_queue()
    free_bytes = _disk_free_bytes()
    if free_bytes >= 0 and free_bytes < LOW_SPACE_BYTES and action != "run_disk_maintenance":
        raise RuntimeError(
            "Deployment-agent storage is full. Run signed disk maintenance before starting another action."
        )
    lifetime = ACTION_TTL_SECONDS.get(action, DEFAULT_TTL_SECONDS) if ttl_seconds is None else int(ttl_seconds)
    if not 30 <= lifetime <= MAX_TTL_SECONDS:
        raise ValueError(f"Queue request lifetime must be between 30 and {MAX_TTL_SECONDS} seconds.")
    now = _utcnow()
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "action": action,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=lifetime)).isoformat(),
        "params": params or {},
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope = {
        "payload_b64": base64.b64encode(payload_bytes).decode("ascii"),
        "signature": hmac.new(SIGNING_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest(),
    }
    target = QUEUE_ROOT / "incoming" / f"{request_id}.json"
    fd, temporary_name = tempfile.mkstemp(prefix=".request-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return {
        "request_id": request_id,
        "action": action,
        "status": "queued",
        "expires_at": payload["expires_at"],
        "emergency_reserve_released": reserve_released,
    }


def get_response(request_id: str) -> dict[str, Any]:
    _require_queue()
    try:
        normalized = str(uuid.UUID(request_id))
    except ValueError as exc:
        raise ValueError("request_id is invalid.") from exc
    path = QUEUE_ROOT / "responses" / f"{normalized}.json"
    if not path.exists():
        return {"request_id": normalized, "status": "pending"}
    with path.open("r", encoding="utf-8-sig") as handle:
        result = json.load(handle)
    # The agent never returns secrets. Keep a strict top-level type here.
    if not isinstance(result, dict):
        raise RuntimeError("The deployment-agent response is invalid.")
    if result.get("status") == "failed" and result.get("action") in {"deploy_approved_release", "promote_exact_candidate"}:
        deployment_id = _validated_rejected_deployment_id(normalized)
        if deployment_id:
            runtime_report = _read_sanitized_deployment_report(deployment_id)
            if runtime_report:
                result = {**result, "deployment_report": runtime_report}
    return result


def get_queue_status() -> dict[str, Any]:
    configured = len(SIGNING_KEY) >= 32
    incoming = QUEUE_ROOT / "incoming"
    responses = QUEUE_ROOT / "responses"
    free_bytes = _disk_free_bytes()
    pending = list(incoming.glob("*.json")) if incoming.exists() else []
    pending_diagnostics = _pending_request_diagnostics(incoming)
    watchdog = _read_agent_watchdog_status()
    connectivity = _read_public_mcp_connectivity_status()
    return {
        "configured": configured,
        "queue_available": incoming.exists() and responses.exists(),
        "pending_requests": len(pending),
        "expired_signed_requests": pending_diagnostics["expired_signed_requests"],
        "oldest_pending_age_seconds": pending_diagnostics["oldest_pending_age_seconds"],
        "completed_responses": len(list(responses.glob("*.json"))) if responses.exists() else 0,
        "transport": "local signed file queue",
        "arbitrary_shell_allowed": False,
        "agent_watchdog": watchdog,
        "agent_processor_healthy": bool(
            watchdog.get("available")
            and not watchdog.get("stale")
            and watchdog.get("status") == "healthy"
            and watchdog.get("task_state_after") == "Running"
        ),
        "public_mcp_connectivity": connectivity,
        "public_mcp_observed_healthy": bool(
            connectivity.get("available")
            and not connectivity.get("stale")
            and connectivity.get("local_mcp") == "healthy"
            and connectivity.get("public_web") == "healthy"
            and connectivity.get("public_api") == "healthy"
            and connectivity.get("public_mcp") == "healthy"
        ),
        "disk_metric_scope": "deployment_queue_filesystem_not_windows_c_drive",
        "disk_free_bytes": free_bytes,
        "low_disk_space": free_bytes >= 0 and free_bytes < LOW_SPACE_BYTES,
        "emergency_reserve_available": RESERVE_PATH.exists(),
        "emergency_reserve_bytes": RESERVE_PATH.stat().st_size if RESERVE_PATH.exists() else 0,
    }
