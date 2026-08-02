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
SIGNING_KEY = os.getenv("PDP_DEPLOYMENT_AGENT_SIGNING_KEY", "")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = 1800
ACTION_TTL_SECONDS = {
    # Layered health can wait behind a long deployment, Windows startup,
    # agent restart, and public-route retries. Other signed actions keep
    # the shorter default lifetime.
    "check_deployment_health": 1800,
}
ALLOWED_ACTIONS = {
    "approve_release",
    "create_final_backup",
    "verify_backup_restore",
    "deploy_approved_release",
    "check_deployment_health",
    "run_disk_maintenance",
    "rollback_deployment",
    "rotate_mcp_token",
}
EMERGENCY_RESERVE_BYTES = max(1024 * 1024, int(os.getenv("PDP_QUEUE_RESERVE_BYTES", str(8 * 1024 * 1024))))
LOW_SPACE_BYTES = max(512 * 1024, int(os.getenv("PDP_QUEUE_LOW_SPACE_BYTES", str(2 * 1024 * 1024))))
RESERVE_PATH = QUEUE_ROOT / ".queue-emergency-reserve"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _disk_free_bytes() -> int:
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
    return result


def get_queue_status() -> dict[str, Any]:
    configured = len(SIGNING_KEY) >= 32
    incoming = QUEUE_ROOT / "incoming"
    responses = QUEUE_ROOT / "responses"
    free_bytes = _disk_free_bytes()
    return {
        "configured": configured,
        "queue_available": incoming.exists() and responses.exists(),
        "pending_requests": len(list(incoming.glob("*.json"))) if incoming.exists() else 0,
        "completed_responses": len(list(responses.glob("*.json"))) if responses.exists() else 0,
        "transport": "local signed file queue",
        "arbitrary_shell_allowed": False,
        "disk_free_bytes": free_bytes,
        "low_disk_space": free_bytes >= 0 and free_bytes < LOW_SPACE_BYTES,
        "emergency_reserve_available": RESERVE_PATH.exists(),
        "emergency_reserve_bytes": RESERVE_PATH.stat().st_size if RESERVE_PATH.exists() else 0,
    }
