"""Durable, non-blocking coordination for parallel PDP One workstreams.

The coordinator stores only public-safe identifiers and signed allowlisted Agent
requests.  It never accepts shell text and never executes a deployment itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import deployment_queue
from deployment_queue import validate_commit, validate_identifier

ROOT = deployment_queue.QUEUE_ROOT / "coordinator"
WORKSTREAMS = ROOT / "workstreams"
PENDING = ROOT / "pending"
HISTORY = ROOT / "history"
LOCK_TTL_MINUTES = 30
LOCK_TTL_MAX_MINUTES = 24 * 60
COORDINATED_REQUEST_TTL_SECONDS = 7 * 24 * 60 * 60
PRIORITIES = {"critical": 0, "infrastructure": 10, "normal": 50, "low": 90}
FINAL_STATES = {"succeeded", "failed", "superseded", "cancelled"}
DISPATCH_POLL_SECONDS = max(2, min(60, int(os.getenv("PDP_COORDINATOR_POLL_SECONDS", "5"))))
_dispatcher_started = False
_dispatcher_guard = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".coordinator-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _safe_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in paths[:200]:
        value = str(raw).strip().replace("\\", "/").lstrip("/")
        if not value or ".." in value.split("/") or len(value) > 240:
            raise ValueError("changed_paths must contain safe repository-relative paths.")
        normalized.append(value)
    return sorted(set(normalized))


def _safe_surfaces(surfaces: list[str]) -> list[str]:
    return sorted({validate_identifier(str(item), "surface") for item in surfaces[:64]})


def _safe_branch(value: str) -> str:
    branch = str(value).strip()
    if not branch or len(branch) > 200 or branch.startswith(("/", ".")) or branch.endswith(("/", ".")):
        raise ValueError("branch is invalid.")
    if ".." in branch or "//" in branch or not all(character.isalnum() or character in "-._/" for character in branch):
        raise ValueError("branch is invalid.")
    return branch


def _load_workstreams() -> list[dict[str, Any]]:
    if not WORKSTREAMS.exists():
        return []
    result = []
    for path in WORKSTREAMS.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                result.append(value)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return result


def _active(item: dict[str, Any], now: datetime | None = None) -> bool:
    if str(item.get("state")) in FINAL_STATES:
        return False
    try:
        return datetime.fromisoformat(str(item["lock_expires_at"]).replace("Z", "+00:00")) > (now or _now())
    except (KeyError, TypeError, ValueError):
        return False


def _conflicts(paths: list[str], surfaces: list[str], workstream_id: str) -> list[dict[str, Any]]:
    path_set, surface_set = set(paths), set(surfaces)
    result = []
    for item in _load_workstreams():
        if item.get("workstream_id") == workstream_id or not _active(item):
            continue
        shared_paths = sorted(path_set.intersection(item.get("changed_paths", [])))
        shared_surfaces = sorted(surface_set.intersection(item.get("surfaces", [])))
        if shared_paths or shared_surfaces:
            result.append({
                "workstream_id": item.get("workstream_id"),
                "shared_paths": shared_paths,
                "shared_surfaces": shared_surfaces,
                "advisory": True,
            })
    return result


def register_workstream(
    workstream_id: str,
    branch: str,
    changed_paths: list[str],
    surfaces: list[str],
    commit_sha: str | None = None,
    pull_request: int | None = None,
    lock_ttl_minutes: int = 120,
) -> dict[str, Any]:
    deployment_queue._require_queue()
    workstream = validate_identifier(workstream_id, "workstream_id")
    safe_branch = _safe_branch(branch)
    ttl = int(lock_ttl_minutes)
    if not LOCK_TTL_MINUTES <= ttl <= LOCK_TTL_MAX_MINUTES:
        raise ValueError("lock_ttl_minutes is outside the supported advisory-lock range.")
    paths, safe_surfaces = _safe_paths(changed_paths), _safe_surfaces(surfaces)
    conflicts = _conflicts(paths, safe_surfaces, workstream)
    now = _now()
    item = {
        "schema": "pdp-one.workstream.v1",
        "workstream_id": workstream,
        "branch": safe_branch,
        "commit_sha": validate_commit(commit_sha) if commit_sha else None,
        "pull_request": int(pull_request) if pull_request else None,
        "changed_paths": paths,
        "surfaces": safe_surfaces,
        "state": "conflict" if conflicts else "developing",
        "conflicts": conflicts,
        "updated_at": now.isoformat(),
        "lock_expires_at": (now + timedelta(minutes=ttl)).isoformat(),
        "soft_lock": True,
    }
    _atomic_json(WORKSTREAMS / f"{workstream}.json", item)
    return item


def heartbeat_workstream(workstream_id: str, state: str = "developing", lock_ttl_minutes: int = 120) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    path = WORKSTREAMS / f"{workstream}.json"
    if not path.exists():
        raise ValueError("Unknown workstream_id.")
    item = json.loads(path.read_text(encoding="utf-8"))
    ttl = int(lock_ttl_minutes)
    if not LOCK_TTL_MINUTES <= ttl <= LOCK_TTL_MAX_MINUTES:
        raise ValueError("lock_ttl_minutes is outside the supported advisory-lock range.")
    allowed = {"developing", "ci_ready", "conflict", "queued", "deploying", "decision_required", *FINAL_STATES}
    if state not in allowed:
        raise ValueError("Unsupported workstream state.")
    now = _now()
    item.update(state=state, updated_at=now.isoformat(), lock_expires_at=(now + timedelta(minutes=ttl)).isoformat())
    _atomic_json(path, item)
    return item


def _signed_envelope(action: str, params: dict[str, Any], ttl_seconds: int) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if action not in {"deploy_approved_release", "promote_exact_candidate"}:
        raise ValueError("The durable coordinator accepts exact deployment actions only.")
    deployment_queue._require_queue()
    request_id = str(uuid.uuid4())
    now = _now()
    payload = {
        "request_id": request_id,
        "action": action,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        "params": params,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope = {
        "payload_b64": base64.b64encode(encoded).decode("ascii"),
        "signature": hmac.new(deployment_queue.SIGNING_KEY.encode("utf-8"), encoded, hashlib.sha256).hexdigest(),
    }
    return request_id, payload, envelope


def _active_agent_request_count() -> int:
    return sum(len(list((deployment_queue.QUEUE_ROOT / name).glob("*.json"))) for name in ("incoming", "processing"))


def queue_exact_deployment(
    workstream_id: str,
    commit_sha: str,
    deployment_id: str,
    preview_id: str,
    priority: str = "normal",
    compatibility_key: str = "application",
    migration_sensitive: bool = False,
    destructive: bool = False,
    contains_commits: list[str] | None = None,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    commit = validate_commit(commit_sha)
    deployment = validate_identifier(deployment_id, "deployment_id")
    preview = validate_identifier(preview_id, "preview_id")
    compatibility = validate_identifier(compatibility_key, "compatibility_key")
    if priority not in PRIORITIES:
        raise ValueError("Unsupported deployment priority.")
    workstream_path = WORKSTREAMS / f"{workstream}.json"
    if not workstream_path.exists():
        raise ValueError("Register the workstream before queueing deployment.")
    idempotency_key = hashlib.sha256(f"{workstream}:{commit}:{deployment}".encode()).hexdigest()
    for root in (PENDING, HISTORY):
        if not root.exists():
            continue
        for path in root.glob("*.json"):
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing.get("idempotency_key") == idempotency_key:
                    return {**existing, "duplicate_suppressed": True}
            except (OSError, json.JSONDecodeError):
                continue
    params = {
        "commit_sha": commit,
        "deployment_id": deployment,
        "preview_id": preview,
        "coordinator_workstream_id": workstream,
    }
    request_id, _, envelope = _signed_envelope("promote_exact_candidate", params, COORDINATED_REQUEST_TTL_SECONDS)
    now = _now()
    record = {
        "schema": "pdp-one.coordinated-deployment.v1",
        "request_id": request_id,
        "workstream_id": workstream,
        "commit_sha": commit,
        "deployment_id": deployment,
        "priority": priority,
        "priority_rank": PRIORITIES[priority],
        "compatibility_key": compatibility,
        "migration_sensitive": bool(migration_sensitive),
        "destructive": bool(destructive),
        "contains_commits": [validate_commit(value) for value in (contains_commits or [])[:32]],
        "idempotency_key": idempotency_key,
        "state": "queued",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "envelope": envelope,
    }
    PENDING.mkdir(parents=True, exist_ok=True)
    # Safe supersession requires explicit ancestry evidence from the caller.
    if not record["migration_sensitive"] and not record["destructive"]:
        for path in PENDING.glob("*.json"):
            try:
                older = json.loads(path.read_text(encoding="utf-8"))
                if (
                    older.get("compatibility_key") == compatibility
                    and older.get("commit_sha") in record["contains_commits"]
                    and not older.get("migration_sensitive")
                    and not older.get("destructive")
                ):
                    older.update(state="superseded", superseded_by=request_id, updated_at=now.isoformat())
                    _atomic_json(HISTORY / f"{older['request_id']}.json", older)
                    path.unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError):
                continue
    target = PENDING / f"{PRIORITIES[priority]:02d}-{now.strftime('%Y%m%d%H%M%S%f')}-{request_id}.json"
    _atomic_json(target, record)
    dispatched = _dispatch_next()
    if dispatched and dispatched.get("request_id") == request_id:
        record.update(state="deploying", dispatched=True, updated_at=dispatched["updated_at"])
    heartbeat_workstream(workstream, "deploying" if record.get("dispatched") else "queued")
    return {key: value for key, value in record.items() if key != "envelope"}


def _dispatch_next() -> dict[str, Any] | None:
    if _active_agent_request_count() or not PENDING.exists():
        return None
    candidates = sorted(PENDING.glob("*.json"), key=lambda path: path.name)
    if not candidates:
        return None
    path = candidates[0]
    record = json.loads(path.read_text(encoding="utf-8"))
    request_id = str(uuid.UUID(str(record["request_id"])))
    incoming = deployment_queue.QUEUE_ROOT / "incoming" / f"{request_id}.json"
    _atomic_json(incoming, record["envelope"])
    record.update(state="deploying", dispatched=True, updated_at=_now().isoformat())
    _atomic_json(HISTORY / f"{request_id}.json", record)
    path.unlink(missing_ok=True)
    return record


def _reconcile_history() -> None:
    if not HISTORY.exists():
        return
    responses = deployment_queue.QUEUE_ROOT / "responses"
    for path in HISTORY.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("state") != "deploying":
                continue
            response_path = responses / f"{record['request_id']}.json"
            if not response_path.exists():
                continue
            response = json.loads(response_path.read_text(encoding="utf-8-sig"))
            response_state = str(response.get("status", "failed"))
            state = "succeeded" if response_state == "succeeded" else "failed"
            record.update(state=state, updated_at=_now().isoformat())
            record.pop("envelope", None)
            _atomic_json(path, record)
            workstream_path = WORKSTREAMS / f"{record['workstream_id']}.json"
            if workstream_path.exists():
                heartbeat_workstream(record["workstream_id"], state)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue


def coordinator_status() -> dict[str, Any]:
    deployment_queue._require_queue()
    _reconcile_history()
    _dispatch_next()
    now = _now()
    workstreams = []
    for item in _load_workstreams():
        visible = dict(item)
        visible["lock_expired"] = not _active(item, now)
        workstreams.append(visible)
    pending = []
    for path in sorted(PENDING.glob("*.json")) if PENDING.exists() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            value.pop("envelope", None)
            pending.append(value)
        except (OSError, json.JSONDecodeError):
            continue
    return {
        "schema": "pdp-one.deployment-coordinator-dashboard.v1",
        "workstreams": sorted(workstreams, key=lambda item: str(item.get("updated_at", "")), reverse=True),
        "pending_deployments": pending,
        "agent": deployment_queue.get_queue_status(),
        "parallel_development_allowed": True,
        "runtime_deployments_serialized": True,
        "arbitrary_shell_allowed": False,
    }


def _dispatcher_loop() -> None:
    while True:
        try:
            _reconcile_history()
            _dispatch_next()
        except Exception:
            # A transient volume/startup error must not terminate MCP or the
            # persistent dispatcher. The next bounded poll retries safely.
            pass
        time.sleep(DISPATCH_POLL_SECONDS)


def start_dispatcher() -> None:
    global _dispatcher_started
    with _dispatcher_guard:
        if _dispatcher_started:
            return
        thread = threading.Thread(target=_dispatcher_loop, name="pdp-deployment-coordinator", daemon=True)
        thread.start()
        _dispatcher_started = True


def register_tools(mcp: Any) -> None:
    from mcp.types import ToolAnnotations

    start_dispatcher()

    @mcp.tool(description="Register or refresh a durable PDP One development workstream and its expiring advisory soft locks.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def register_development_workstream(workstream_id: str, branch: str, changed_paths: list[str], surfaces: list[str], commit_sha: str | None = None, pull_request: int | None = None, lock_ttl_minutes: int = 120) -> dict:
        return register_workstream(workstream_id, branch, changed_paths, surfaces, commit_sha, pull_request, lock_ttl_minutes)

    @mcp.tool(description="Refresh an existing workstream heartbeat or record its durable lifecycle state.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def update_development_workstream(workstream_id: str, state: str = "developing", lock_ttl_minutes: int = 120) -> dict:
        return heartbeat_workstream(workstream_id, state, lock_ttl_minutes)

    @mcp.tool(description="Queue one exact tested commit for durable, priority-aware, serialized deployment. Duplicate requests are suppressed.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def queue_coordinated_deployment(workstream_id: str, commit_sha: str, deployment_id: str, preview_id: str, priority: str = "normal", compatibility_key: str = "application", migration_sensitive: bool = False, destructive: bool = False, contains_commits: list[str] | None = None) -> dict:
        return queue_exact_deployment(workstream_id, commit_sha, deployment_id, preview_id, priority, compatibility_key, migration_sensitive, destructive, contains_commits)

    @mcp.tool(description="Return the durable multi-chat workstream and deployment dashboard, including conflicts, queue priority and Agent health.", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def get_development_coordination_status() -> dict:
        return coordinator_status()
