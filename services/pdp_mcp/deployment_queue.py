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
    # Layered health may wait for Windows startup and public-route retries.
    # Keep other signed actions on the shorter default lifetime.
    "check_deployment_health": 1200,
}
ALLOWED_ACTIONS = {
    "approve_release",
    "create_final_backup",
    "verify_backup_restore",
    "deploy_approved_release",
    "check_deployment_health",
    "rollback_deployment",
    "rotate_mcp_token",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_queue() -> None:
    if len(SIGNING_KEY) < 32:
        raise RuntimeError("The local deployment agent signing key is not configured.")
    for name in ("incoming", "responses"):
        (QUEUE_ROOT / name).mkdir(parents=True, exist_ok=True)


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
    _require_queue()
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported deployment-agent action.")
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
    return {"request_id": request_id, "action": action, "status": "queued", "expires_at": payload["expires_at"]}


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
    return {
        "configured": configured,
        "queue_available": incoming.exists() and responses.exists(),
        "pending_requests": len(list(incoming.glob("*.json"))) if incoming.exists() else 0,
        "completed_responses": len(list(responses.glob("*.json"))) if responses.exists() else 0,
        "transport": "local signed file queue",
        "arbitrary_shell_allowed": False,
    }
