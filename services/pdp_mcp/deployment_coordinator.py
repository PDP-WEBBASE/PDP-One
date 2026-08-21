"""Durable, non-blocking coordination for parallel PDP One workstreams.

The coordinator stores only public-safe identifiers and signed allowlisted Agent
requests. It never accepts shell text and never executes a deployment itself.

V2 extends the original deployment dispatcher with durable workstream/candidate
identity, exact evidence attribution, atomic coordination leases and promotion
lifecycle controls while keeping existing V1 tool calls backward compatible.
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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import deployment_queue
from deployment_queue import validate_commit, validate_identifier

ROOT = deployment_queue.QUEUE_ROOT / "coordinator"
WORKSTREAMS = ROOT / "workstreams"
PENDING = ROOT / "pending"
HISTORY = ROOT / "history"
LIVE_TEST_LEASES = ROOT / "live-test-leases"
PROMOTION_LEASE = ROOT / "promotion-lease.json"
MUTATION_LOCK = ROOT / ".mutation-lock"

LOCK_TTL_MINUTES = 30
LOCK_TTL_MAX_MINUTES = 24 * 60
COORDINATED_REQUEST_TTL_SECONDS = 7 * 24 * 60 * 60
PROMOTION_LEASE_MINUTES = 30
PROMOTION_LEASE_MAX_MINUTES = 6 * 60
MUTATION_LOCK_TIMEOUT_SECONDS = 5
MUTATION_LOCK_STALE_SECONDS = 30
PRIORITIES = {"critical": 0, "infrastructure": 10, "normal": 50, "low": 90}

LEGACY_FINAL_STATES = {"succeeded", "failed", "superseded", "cancelled"}
WORKSTREAM_FINAL_STATES = {"merged", "closed", "superseded", "cancelled"}
CANDIDATE_FINAL_STATES = {"merged", "closed", "superseded", "cancelled"}
AUTO_RENEW_STATES = {
    "ready",
    "waiting_dependency",
    "promotion_reserved",
    "verifying",
    "queued",
    "deploying",
    "acceptance",
    "pre_merge",
}
WORKSTREAM_STATES = {
    "developing",
    "ci_ready",
    "ready",
    "waiting_dependency",
    "conflict",
    "promotion_reserved",
    "verifying",
    "queued",
    "deploying",
    "acceptance",
    "pre_merge",
    "decision_required",
    "blocked",
    "merged",
    "closed",
    "superseded",
    "cancelled",
    "succeeded",
    "failed",
}
EVIDENCE_SUCCESS = {"success", "succeeded", "passed", "healthy", "skipped"}
DISPATCH_POLL_SECONDS = max(2, min(60, int(os.getenv("PDP_COORDINATOR_POLL_SECONDS", "5"))))
_dispatcher_started = False
_dispatcher_guard = threading.Lock()
_process_mutation_guard = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Coordinator record must be a JSON object.")
    return value


@contextmanager
def _coordinator_mutation_lock(timeout_seconds: int = MUTATION_LOCK_TIMEOUT_SECONDS):
    """Cross-thread/process bounded lock for conflict-check + write sequences."""
    with _process_mutation_guard:
        ROOT.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(1, int(timeout_seconds))
        while True:
            try:
                MUTATION_LOCK.mkdir()
                break
            except FileExistsError:
                try:
                    age = max(0.0, time.time() - MUTATION_LOCK.stat().st_mtime)
                    if age > MUTATION_LOCK_STALE_SECONDS:
                        MUTATION_LOCK.rmdir()
                        continue
                except (FileNotFoundError, OSError):
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("Coordinator mutation lock is busy; retry from a fresh concurrency sync.")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                MUTATION_LOCK.rmdir()
            except FileNotFoundError:
                pass


def _safe_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in paths[:200]:
        value = str(raw).strip().replace("\\", "/").lstrip("/")
        if not value or ".." in value.split("/") or len(value) > 240:
            raise ValueError("changed_paths must contain safe repository-relative paths.")
        normalized.append(value)
    return sorted(set(normalized))


def _safe_identifier_list(values: list[str] | None, field: str, limit: int = 64) -> list[str]:
    return sorted({validate_identifier(str(value), field) for value in (values or [])[:limit]})


def _safe_surfaces(surfaces: list[str]) -> list[str]:
    return _safe_identifier_list(surfaces, "surface")


def _safe_public_ref(value: str | None, field: str, max_length: int = 160) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > max_length or any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{field} must be a short public-safe reference.")
    return normalized


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
            result.append(_read_json(path))
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return result


def _is_v2(item: dict[str, Any]) -> bool:
    return str(item.get("schema")) == "pdp-one.workstream.v2"


def _is_final(item: dict[str, Any]) -> bool:
    state = str(item.get("state", ""))
    if _is_v2(item):
        return state in WORKSTREAM_FINAL_STATES
    return state in LEGACY_FINAL_STATES


def _active(item: dict[str, Any], now: datetime | None = None) -> bool:
    if _is_final(item):
        return False
    expiry = _parse_time(item.get("lock_expires_at"))
    return bool(expiry and expiry > (now or _now()))


def _scope_conflicts(item: dict[str, Any], other: dict[str, Any]) -> dict[str, Any] | None:
    fields = (
        ("changed_paths", "shared_paths"),
        ("surfaces", "shared_surfaces"),
        ("components", "shared_components"),
        ("runtime_resources", "shared_runtime_resources"),
        ("database_resources", "shared_database_resources"),
    )
    conflict: dict[str, Any] = {"workstream_id": other.get("workstream_id"), "advisory": True}
    has_overlap = False
    for source, output in fields:
        shared = sorted(set(item.get(source, [])).intersection(other.get(source, [])))
        conflict[output] = shared
        has_overlap = has_overlap or bool(shared)
    return conflict if has_overlap else None


def _conflicts_for_item(item: dict[str, Any], workstreams: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    now = _now()
    result = []
    for other in workstreams if workstreams is not None else _load_workstreams():
        if other.get("workstream_id") == item.get("workstream_id") or not _active(other, now):
            continue
        conflict = _scope_conflicts(item, other)
        if conflict:
            result.append(conflict)
    return sorted(result, key=lambda value: str(value.get("workstream_id", "")))


def _candidate_id(workstream_id: str, head_sha: str) -> str:
    digest = hashlib.sha256(f"{workstream_id}:{head_sha}".encode("utf-8")).hexdigest()[:10]
    return f"cand-{head_sha[:12]}-{digest}"


def _candidate_evidence_state(candidate: dict[str, Any]) -> str:
    if str(candidate.get("state")) == "stale":
        return "stale"
    evidence = candidate.get("evidence") or {}
    required = candidate.get("required_evidence") or []
    for kind in required:
        record = evidence.get(kind)
        if not isinstance(record, dict):
            return "pending"
        if str(record.get("head_sha")) != str(candidate.get("head_sha")):
            return "stale"
        if str(record.get("result", "")).lower() not in EVIDENCE_SUCCESS:
            return "pending"
    return "ready" if required else "not_required"


def _upsert_candidate_unlocked(
    item: dict[str, Any],
    head_sha: str,
    base_sha: str | None = None,
    pull_request: int | None = None,
    required_evidence: list[str] | None = None,
    current_main_sha: str | None = None,
) -> dict[str, Any]:
    head = validate_commit(head_sha)
    candidate_id = _candidate_id(str(item["workstream_id"]), head)
    candidates = item.setdefault("candidates", {})
    previous_id = item.get("current_candidate_id")
    if previous_id and previous_id != candidate_id:
        previous = candidates.get(previous_id)
        if isinstance(previous, dict) and str(previous.get("state")) not in CANDIDATE_FINAL_STATES:
            previous["state"] = "stale"
            previous["evidence_state"] = "stale"
            previous["stale_reason"] = "workstream_head_changed"
            previous["updated_at"] = _now().isoformat()
    now = _now().isoformat()
    candidate = candidates.get(candidate_id)
    if not isinstance(candidate, dict):
        candidate = {
            "schema": "pdp-one.candidate.v1",
            "candidate_id": candidate_id,
            "head_sha": head,
            "base_sha": validate_commit(base_sha) if base_sha else None,
            "pull_request": int(pull_request) if pull_request else None,
            "required_evidence": _safe_identifier_list(required_evidence if required_evidence is not None else ["public-boundary", "verify"], "evidence_kind"),
            "evidence": {},
            "evidence_state": "pending",
            "state": "developing",
            "created_at": now,
            "updated_at": now,
        }
        candidates[candidate_id] = candidate
    else:
        if base_sha:
            candidate["base_sha"] = validate_commit(base_sha)
        if pull_request:
            candidate["pull_request"] = int(pull_request)
        if required_evidence is not None:
            candidate["required_evidence"] = _safe_identifier_list(required_evidence, "evidence_kind")
        candidate["updated_at"] = now
        if candidate.get("state") == "stale":
            candidate["state"] = "developing"
            candidate.pop("stale_reason", None)
    if current_main_sha:
        candidate["observed_main_sha"] = validate_commit(current_main_sha)
    candidate["evidence_state"] = _candidate_evidence_state(candidate)
    item["current_candidate_id"] = candidate_id
    item["commit_sha"] = head
    item["pull_request"] = candidate.get("pull_request") or item.get("pull_request")
    item["base_sha"] = candidate.get("base_sha")
    item["current_main_sha"] = candidate.get("observed_main_sha") or item.get("current_main_sha")
    return candidate


def _dependency_blockers(item: dict[str, Any], workstreams: list[dict[str, Any]] | None = None) -> list[str]:
    dependencies = item.get("dependencies") or {}
    target_ids = set(dependencies.get("blocked_by", [])) | set(dependencies.get("requires", []))
    if not target_ids:
        return []
    available = {str(value.get("workstream_id")): value for value in (workstreams or _load_workstreams())}
    blockers = []
    for target in sorted(target_ids):
        other = available.get(target)
        if other is None or not _is_final(other):
            blockers.append(target)
    return blockers


def _promotion_lease_unlocked(now: datetime | None = None) -> dict[str, Any] | None:
    if not PROMOTION_LEASE.exists():
        return None
    try:
        lease = _read_json(PROMOTION_LEASE)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    expiry = _parse_time(lease.get("expires_at"))
    if not expiry or expiry <= (now or _now()):
        PROMOTION_LEASE.unlink(missing_ok=True)
        return None
    return lease


def _release_promotion_lease_unlocked(workstream_id: str | None = None) -> None:
    lease = _promotion_lease_unlocked()
    if not lease:
        return
    if workstream_id and str(lease.get("workstream_id")) != workstream_id:
        return
    PROMOTION_LEASE.unlink(missing_ok=True)


def _renew_lifecycle_leases_unlocked() -> None:
    now = _now()
    workstreams = _load_workstreams()
    for item in workstreams:
        if not _is_v2(item) or _is_final(item):
            continue
        if str(item.get("state")) not in AUTO_RENEW_STATES:
            continue
        expiry = _parse_time(item.get("lock_expires_at"))
        if expiry and expiry > now + timedelta(minutes=30):
            continue
        item["lock_expires_at"] = (now + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
        item["updated_at"] = now.isoformat()
        _atomic_json(WORKSTREAMS / f"{item['workstream_id']}.json", item)


def register_workstream(
    workstream_id: str,
    branch: str,
    changed_paths: list[str],
    surfaces: list[str],
    commit_sha: str | None = None,
    pull_request: int | None = None,
    lock_ttl_minutes: int = 120,
    origin_chat_ref: str | None = None,
    blocked_by: list[str] | None = None,
    requires: list[str] | None = None,
    integrates_with: list[str] | None = None,
    supersedes: list[str] | None = None,
    components: list[str] | None = None,
    runtime_resources: list[str] | None = None,
    database_resources: list[str] | None = None,
    live_test_scopes: list[str] | None = None,
    base_sha: str | None = None,
    current_main_sha: str | None = None,
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    deployment_queue._require_queue()
    workstream = validate_identifier(workstream_id, "workstream_id")
    safe_branch = _safe_branch(branch)
    ttl = int(lock_ttl_minutes)
    if not LOCK_TTL_MINUTES <= ttl <= LOCK_TTL_MAX_MINUTES:
        raise ValueError("lock_ttl_minutes is outside the supported advisory-lock range.")
    with _coordinator_mutation_lock():
        _renew_lifecycle_leases_unlocked()
        path = WORKSTREAMS / f"{workstream}.json"
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = _read_json(path)
            except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                existing = {}
        v2_requested = any(
            value is not None
            for value in (
                origin_chat_ref,
                blocked_by,
                requires,
                integrates_with,
                supersedes,
                components,
                runtime_resources,
                database_resources,
                live_test_scopes,
                base_sha,
                current_main_sha,
                required_evidence,
            )
        )
        use_v2 = _is_v2(existing) or v2_requested
        now = _now()
        item: dict[str, Any] = {
            "schema": "pdp-one.workstream.v2" if use_v2 else "pdp-one.workstream.v1",
            "workstream_id": workstream,
            "branch": safe_branch,
            "commit_sha": existing.get("commit_sha"),
            "pull_request": int(pull_request) if pull_request else existing.get("pull_request"),
            "changed_paths": _safe_paths(changed_paths),
            "surfaces": _safe_surfaces(surfaces),
            "components": _safe_identifier_list(components, "component"),
            "runtime_resources": _safe_identifier_list(runtime_resources, "runtime_resource"),
            "database_resources": _safe_identifier_list(database_resources, "database_resource"),
            "live_test_scopes": _safe_identifier_list(live_test_scopes, "live_test_scope"),
            "dependencies": {
                "blocked_by": _safe_identifier_list(blocked_by, "workstream_id"),
                "requires": _safe_identifier_list(requires, "workstream_id"),
                "integrates_with": _safe_identifier_list(integrates_with, "workstream_id"),
                "supersedes": _safe_identifier_list(supersedes, "workstream_id"),
            },
            "origin_chat_ref": existing.get("origin_chat_ref") or _safe_public_ref(origin_chat_ref, "origin_chat_ref"),
            "continuation_chat_ref": existing.get("continuation_chat_ref") or existing.get("origin_chat_ref") or _safe_public_ref(origin_chat_ref, "origin_chat_ref"),
            "automatic_cross_chat_takeover": False,
            "handoff_history": list(existing.get("handoff_history") or []),
            "candidates": dict(existing.get("candidates") or {}),
            "current_candidate_id": existing.get("current_candidate_id"),
            "state": str(existing.get("state") or "developing"),
            "created_at": existing.get("created_at") or now.isoformat(),
            "updated_at": now.isoformat(),
            "lock_expires_at": (now + timedelta(minutes=ttl)).isoformat(),
            "soft_lock": True,
            "promotion_state": existing.get("promotion_state") or "development",
            "external_state": dict(existing.get("external_state") or {}),
        }
        if base_sha:
            item["base_sha"] = validate_commit(base_sha)
        if current_main_sha:
            item["current_main_sha"] = validate_commit(current_main_sha)
        if commit_sha:
            _upsert_candidate_unlocked(
                item,
                commit_sha,
                base_sha=base_sha,
                pull_request=pull_request,
                required_evidence=required_evidence,
                current_main_sha=current_main_sha,
            )
        workstreams = [value for value in _load_workstreams() if value.get("workstream_id") != workstream]
        conflicts = _conflicts_for_item(item, workstreams)
        item["conflicts"] = conflicts
        item["dependency_blockers"] = _dependency_blockers(item, workstreams + [item])
        if conflicts:
            item["state"] = "conflict"
        elif item["dependency_blockers"] and item["state"] in {"developing", "ci_ready", "ready", "waiting_dependency"}:
            item["state"] = "waiting_dependency"
        elif item["state"] == "conflict":
            item["state"] = "developing"
        _atomic_json(path, item)
        return item


def _heartbeat_workstream_unlocked(workstream_id: str, state: str, lock_ttl_minutes: int) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    path = WORKSTREAMS / f"{workstream}.json"
    if not path.exists():
        raise ValueError("Unknown workstream_id.")
    item = _read_json(path)
    ttl = int(lock_ttl_minutes)
    if not LOCK_TTL_MINUTES <= ttl <= LOCK_TTL_MAX_MINUTES:
        raise ValueError("lock_ttl_minutes is outside the supported advisory-lock range.")
    if state not in WORKSTREAM_STATES:
        raise ValueError("Unsupported workstream state.")
    if _is_v2(item):
        if state == "succeeded":
            state = "acceptance"
        elif state == "failed":
            state = "decision_required"
        if state in AUTO_RENEW_STATES:
            ttl = LOCK_TTL_MAX_MINUTES
    now = _now()
    item.update(state=state, updated_at=now.isoformat(), lock_expires_at=(now + timedelta(minutes=ttl)).isoformat())
    if _is_v2(item) and state in WORKSTREAM_FINAL_STATES:
        _release_promotion_lease_unlocked(workstream)
    _atomic_json(path, item)
    return item


def heartbeat_workstream(workstream_id: str, state: str = "developing", lock_ttl_minutes: int = 120) -> dict[str, Any]:
    with _coordinator_mutation_lock():
        return _heartbeat_workstream_unlocked(workstream_id, state, lock_ttl_minutes)


def record_workstream_handoff(
    workstream_id: str,
    from_chat_ref: str,
    to_chat_ref: str,
    owner_requested: bool,
) -> dict[str, Any]:
    if not owner_requested:
        raise ValueError("Cross-chat continuation requires an explicit owner-requested handoff.")
    workstream = validate_identifier(workstream_id, "workstream_id")
    from_ref = _safe_public_ref(from_chat_ref, "from_chat_ref")
    to_ref = _safe_public_ref(to_chat_ref, "to_chat_ref")
    if not from_ref or not to_ref:
        raise ValueError("Both handoff chat references are required.")
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        if not _is_v2(item):
            raise ValueError("Handoff history requires a V2 workstream registration.")
        now = _now().isoformat()
        item.setdefault("handoff_history", []).append({
            "from_chat_ref": from_ref,
            "to_chat_ref": to_ref,
            "owner_requested": True,
            "recorded_at": now,
        })
        item["continuation_chat_ref"] = to_ref
        item["updated_at"] = now
        _atomic_json(path, item)
        return item


def register_candidate(
    workstream_id: str,
    commit_sha: str,
    base_sha: str,
    pull_request: int | None = None,
    current_main_sha: str | None = None,
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Register the workstream before registering a candidate.")
        item = _read_json(path)
        if not _is_v2(item):
            raise ValueError("Candidate lineage requires a V2 workstream registration.")
        candidate = _upsert_candidate_unlocked(
            item,
            commit_sha,
            base_sha=base_sha,
            pull_request=pull_request,
            required_evidence=required_evidence,
            current_main_sha=current_main_sha,
        )
        item["state"] = "developing"
        item["promotion_state"] = "development"
        item["updated_at"] = _now().isoformat()
        _atomic_json(path, item)
        return candidate


def record_candidate_evidence(
    workstream_id: str,
    candidate_id: str,
    evidence_kind: str,
    evidence_id: str,
    result: str,
    head_sha: str,
    details_ref: str | None = None,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    candidate_key = validate_identifier(candidate_id, "candidate_id")
    kind = validate_identifier(evidence_kind, "evidence_kind")
    evidence_ref = _safe_public_ref(evidence_id, "evidence_id", 200)
    if not evidence_ref:
        raise ValueError("evidence_id is required.")
    exact_head = validate_commit(head_sha)
    normalized_result = validate_identifier(str(result).lower(), "evidence_result")
    detail = _safe_public_ref(details_ref, "details_ref", 240)
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        candidate = (item.get("candidates") or {}).get(candidate_key)
        if not isinstance(candidate, dict):
            raise ValueError("Unknown candidate_id.")
        if str(candidate.get("head_sha")) != exact_head:
            raise ValueError("Evidence head SHA does not match the candidate exact head.")
        now = _now().isoformat()
        evidence = {
            "kind": kind,
            "evidence_id": evidence_ref,
            "result": normalized_result,
            "head_sha": exact_head,
            "recorded_at": now,
        }
        if detail:
            evidence["details_ref"] = detail
        candidate.setdefault("evidence", {})[kind] = evidence
        if item.get("current_candidate_id") != candidate_key or item.get("commit_sha") != exact_head:
            candidate["state"] = "stale"
            candidate["evidence_state"] = "stale"
        else:
            candidate["evidence_state"] = _candidate_evidence_state(candidate)
            if candidate["evidence_state"] == "ready" and candidate.get("state") in {"developing", "verifying"}:
                candidate["state"] = "ready"
                item["state"] = "ready"
        candidate["updated_at"] = now
        item["updated_at"] = now
        _atomic_json(path, item)
        return candidate


def reserve_promotion(
    workstream_id: str,
    candidate_id: str,
    head_sha: str,
    current_main_sha: str,
    lease_minutes: int = 120,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    candidate_key = validate_identifier(candidate_id, "candidate_id")
    head = validate_commit(head_sha)
    current_main = validate_commit(current_main_sha)
    lease_ttl = int(lease_minutes)
    if not PROMOTION_LEASE_MINUTES <= lease_ttl <= PROMOTION_LEASE_MAX_MINUTES:
        raise ValueError("promotion lease duration is outside the supported range.")
    with _coordinator_mutation_lock():
        _renew_lifecycle_leases_unlocked()
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        if not _is_v2(item):
            raise ValueError("Promotion lease requires a V2 workstream.")
        candidate = (item.get("candidates") or {}).get(candidate_key)
        if not isinstance(candidate, dict):
            raise ValueError("Unknown candidate_id.")
        if item.get("current_candidate_id") != candidate_key or item.get("commit_sha") != head or candidate.get("head_sha") != head:
            raise ValueError("Only the current exact candidate may reserve promotion.")
        if candidate.get("base_sha") != current_main:
            raise ValueError("Candidate is not integrated on the exact current main; refresh once before promotion.")
        all_workstreams = _load_workstreams()
        conflicts = _conflicts_for_item(item, all_workstreams)
        blockers = _dependency_blockers(item, all_workstreams)
        if conflicts:
            raise ValueError("Workstream has active scope conflicts and cannot reserve promotion.")
        if blockers:
            raise ValueError("Workstream dependencies are not terminal and promotion is blocked.")
        existing = _promotion_lease_unlocked()
        if existing and str(existing.get("workstream_id")) != workstream:
            raise ValueError("Another workstream currently holds the promotion lease.")
        now = _now()
        lease = {
            "schema": "pdp-one.promotion-lease.v1",
            "workstream_id": workstream,
            "candidate_id": candidate_key,
            "head_sha": head,
            "base_sha": candidate.get("base_sha"),
            "current_main_sha": current_main,
            "acquired_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=lease_ttl)).isoformat(),
        }
        _atomic_json(PROMOTION_LEASE, lease)
        candidate["state"] = "promotion_reserved"
        candidate["updated_at"] = now.isoformat()
        item["state"] = "promotion_reserved"
        item["promotion_state"] = "reserved"
        item["current_main_sha"] = current_main
        item["lock_expires_at"] = (now + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
        item["updated_at"] = now.isoformat()
        _atomic_json(path, item)
        return lease


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


def _iter_deployment_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for root in (PENDING, HISTORY):
        if not root.exists():
            continue
        for path in root.glob("*.json"):
            try:
                records.append(_read_json(path))
            except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                continue
    return records


def _effective_priority_rank(record: dict[str, Any], now: datetime | None = None) -> int:
    rank = int(record.get("priority_rank", PRIORITIES.get(str(record.get("priority")), 50)))
    created = _parse_time(record.get("created_at")) or (now or _now())
    age_hours = max(0.0, ((now or _now()) - created).total_seconds() / 3600.0)
    aging_credit = min(30, int(age_hours // 6) * 5)
    return max(0, rank - aging_credit)


def _pending_sort_key(path: Path) -> tuple[int, str, str]:
    try:
        record = _read_json(path)
        return (_effective_priority_rank(record), str(record.get("created_at", "")), path.name)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return (999, "", path.name)


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
    candidate_id: str | None = None,
    current_main_sha: str | None = None,
    allow_redeploy: bool = False,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    commit = validate_commit(commit_sha)
    deployment = validate_identifier(deployment_id, "deployment_id")
    preview = validate_identifier(preview_id, "preview_id")
    compatibility = validate_identifier(compatibility_key, "compatibility_key")
    if priority not in PRIORITIES:
        raise ValueError("Unsupported deployment priority.")
    with _coordinator_mutation_lock():
        workstream_path = WORKSTREAMS / f"{workstream}.json"
        if not workstream_path.exists():
            raise ValueError("Register the workstream before queueing deployment.")
        item = _read_json(workstream_path)
        candidate_key = validate_identifier(candidate_id, "candidate_id") if candidate_id else None
        current_main = validate_commit(current_main_sha) if current_main_sha else None
        candidate: dict[str, Any] | None = None
        if _is_v2(item):
            if not candidate_key or not current_main:
                raise ValueError("V2 deployment requires candidate_id and exact current_main_sha.")
            candidate = (item.get("candidates") or {}).get(candidate_key)
            if not isinstance(candidate, dict):
                raise ValueError("Unknown candidate_id.")
            if item.get("current_candidate_id") != candidate_key or candidate.get("head_sha") != commit or item.get("commit_sha") != commit:
                raise ValueError("Deployment commit must match the current exact candidate.")
            if candidate.get("base_sha") != current_main:
                raise ValueError("Old-base candidate deployment is forbidden; refresh on exact current main first.")
            lease = _promotion_lease_unlocked()
            if not lease or lease.get("workstream_id") != workstream or lease.get("candidate_id") != candidate_key or lease.get("head_sha") != commit:
                raise ValueError("The exact candidate does not hold the promotion lease.")
            evidence_state = _candidate_evidence_state(candidate)
            candidate["evidence_state"] = evidence_state
            if evidence_state not in {"ready", "not_required"}:
                raise ValueError("Required exact-head evidence is not complete for this candidate.")
        legacy_idempotency_key = hashlib.sha256(f"{workstream}:{commit}:{deployment}".encode()).hexdigest()
        exact_candidate_key = hashlib.sha256(f"{compatibility}:{commit}".encode()).hexdigest()
        for existing in _iter_deployment_records():
            if existing.get("idempotency_key") == legacy_idempotency_key:
                return {**existing, "duplicate_suppressed": True}
            if (
                _is_v2(item)
                and not allow_redeploy
                and existing.get("exact_candidate_key") == exact_candidate_key
                and existing.get("state") not in {"failed", "cancelled", "superseded"}
            ):
                return {**existing, "duplicate_suppressed": True, "duplicate_reason": "same_exact_candidate"}
        params = {
            "commit_sha": commit,
            "deployment_id": deployment,
            "preview_id": preview,
            "coordinator_workstream_id": workstream,
        }
        if candidate_key:
            params["coordinator_candidate_id"] = candidate_key
        request_id, _, envelope = _signed_envelope("promote_exact_candidate", params, COORDINATED_REQUEST_TTL_SECONDS)
        now = _now()
        record = {
            "schema": "pdp-one.coordinated-deployment.v2" if _is_v2(item) else "pdp-one.coordinated-deployment.v1",
            "request_id": request_id,
            "workstream_id": workstream,
            "candidate_id": candidate_key,
            "commit_sha": commit,
            "current_main_sha": current_main,
            "deployment_id": deployment,
            "priority": priority,
            "priority_rank": PRIORITIES[priority],
            "compatibility_key": compatibility,
            "migration_sensitive": bool(migration_sensitive),
            "destructive": bool(destructive),
            "contains_commits": [validate_commit(value) for value in (contains_commits or [])[:32]],
            "idempotency_key": legacy_idempotency_key,
            "exact_candidate_key": exact_candidate_key,
            "state": "queued",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "envelope": envelope,
        }
        PENDING.mkdir(parents=True, exist_ok=True)
        if not _is_v2(item) and not record["migration_sensitive"] and not record["destructive"]:
            for path in PENDING.glob("*.json"):
                try:
                    older = _read_json(path)
                    if (
                        older.get("compatibility_key") == compatibility
                        and older.get("commit_sha") in record["contains_commits"]
                        and not older.get("migration_sensitive")
                        and not older.get("destructive")
                    ):
                        older.update(state="superseded", superseded_by=request_id, updated_at=now.isoformat())
                        _atomic_json(HISTORY / f"{older['request_id']}.json", older)
                        path.unlink(missing_ok=True)
                except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    continue
        target = PENDING / f"{PRIORITIES[priority]:02d}-{now.strftime('%Y%m%d%H%M%S%f')}-{request_id}.json"
        _atomic_json(target, record)
        if candidate is not None:
            candidate["state"] = "queued"
            candidate["deployment"] = {
                "request_id": request_id,
                "deployment_id": deployment,
                "commit_sha": commit,
                "state": "queued",
                "recorded_at": now.isoformat(),
            }
            candidate["updated_at"] = now.isoformat()
            item["state"] = "queued"
            item["promotion_state"] = "queued"
            item["lock_expires_at"] = (now + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
            item["updated_at"] = now.isoformat()
            _atomic_json(workstream_path, item)
        dispatched = _dispatch_next_unlocked()
        if dispatched and dispatched.get("request_id") == request_id:
            record.update(state="deploying", dispatched=True, updated_at=dispatched["updated_at"])
        if not _is_v2(item):
            _heartbeat_workstream_unlocked(workstream, "deploying" if record.get("dispatched") else "queued", 120)
        return {key: value for key, value in record.items() if key != "envelope"}


def _dispatch_next_unlocked() -> dict[str, Any] | None:
    if _active_agent_request_count() or not PENDING.exists():
        return None
    candidates = sorted(PENDING.glob("*.json"), key=_pending_sort_key)
    if not candidates:
        return None
    path = candidates[0]
    record = _read_json(path)
    request_id = str(uuid.UUID(str(record["request_id"])))
    incoming = deployment_queue.QUEUE_ROOT / "incoming" / f"{request_id}.json"
    _atomic_json(incoming, record["envelope"])
    record.update(state="deploying", dispatched=True, updated_at=_now().isoformat())
    _atomic_json(HISTORY / f"{request_id}.json", record)
    path.unlink(missing_ok=True)
    workstream_path = WORKSTREAMS / f"{record['workstream_id']}.json"
    if workstream_path.exists():
        item = _read_json(workstream_path)
        if _is_v2(item):
            candidate = (item.get("candidates") or {}).get(record.get("candidate_id"))
            if isinstance(candidate, dict):
                candidate["state"] = "deploying"
                if isinstance(candidate.get("deployment"), dict):
                    candidate["deployment"]["state"] = "deploying"
                candidate["updated_at"] = _now().isoformat()
            item["state"] = "deploying"
            item["promotion_state"] = "deploying"
            item["lock_expires_at"] = (_now() + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
            item["updated_at"] = _now().isoformat()
            _atomic_json(workstream_path, item)
    return record


def _reconcile_history_unlocked() -> None:
    if not HISTORY.exists():
        return
    responses = deployment_queue.QUEUE_ROOT / "responses"
    for path in HISTORY.glob("*.json"):
        try:
            record = _read_json(path)
            if record.get("state") != "deploying":
                continue
            response_path = responses / f"{record['request_id']}.json"
            if not response_path.exists():
                continue
            response = json.loads(response_path.read_text(encoding="utf-8-sig"))
            response_state = str(response.get("status", "failed"))
            state = "succeeded" if response_state == "succeeded" else "failed"
            now = _now()
            record.update(state=state, updated_at=now.isoformat())
            record.pop("envelope", None)
            _atomic_json(path, record)
            workstream_path = WORKSTREAMS / f"{record['workstream_id']}.json"
            if not workstream_path.exists():
                continue
            item = _read_json(workstream_path)
            if not _is_v2(item):
                _heartbeat_workstream_unlocked(record["workstream_id"], state, 120)
                continue
            candidate = (item.get("candidates") or {}).get(record.get("candidate_id"))
            if not isinstance(candidate, dict):
                item["state"] = "decision_required"
                item["decision_reason"] = "deployment_result_candidate_identity_missing"
                _release_promotion_lease_unlocked(str(item.get("workstream_id")))
            elif state == "succeeded":
                candidate["state"] = "acceptance"
                candidate.setdefault("deployment", {}).update(
                    state="succeeded",
                    request_id=record["request_id"],
                    deployment_id=record["deployment_id"],
                    commit_sha=record["commit_sha"],
                    completed_at=now.isoformat(),
                )
                item["state"] = "acceptance"
                item["promotion_state"] = "acceptance"
                item["lock_expires_at"] = (now + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
            else:
                candidate["state"] = "decision_required"
                candidate.setdefault("deployment", {}).update(state="failed", completed_at=now.isoformat())
                item["state"] = "decision_required"
                item["promotion_state"] = "released_after_failure"
                _release_promotion_lease_unlocked(str(item.get("workstream_id")))
            candidate["updated_at"] = now.isoformat()
            item["updated_at"] = now.isoformat()
            _atomic_json(workstream_path, item)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue


def record_candidate_acceptance(
    workstream_id: str,
    candidate_id: str,
    head_sha: str,
    deployment_request_id: str,
    deployment_id: str,
    health_request_id: str,
    result: str,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    candidate_key = validate_identifier(candidate_id, "candidate_id")
    head = validate_commit(head_sha)
    request_id = str(uuid.UUID(str(deployment_request_id)))
    health_id = str(uuid.UUID(str(health_request_id)))
    deployment = validate_identifier(deployment_id, "deployment_id")
    normalized_result = validate_identifier(str(result).lower(), "acceptance_result")
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        candidate = (item.get("candidates") or {}).get(candidate_key)
        if not isinstance(candidate, dict) or candidate.get("head_sha") != head:
            raise ValueError("Acceptance identity does not match the exact candidate.")
        history_path = HISTORY / f"{request_id}.json"
        if not history_path.exists():
            raise ValueError("Deployment request evidence is missing from coordinator history.")
        deployment_record = _read_json(history_path)
        if (
            deployment_record.get("workstream_id") != workstream
            or deployment_record.get("candidate_id") != candidate_key
            or deployment_record.get("commit_sha") != head
            or deployment_record.get("deployment_id") != deployment
            or deployment_record.get("state") != "succeeded"
        ):
            raise ValueError("Deployment evidence does not match this exact candidate.")
        now = _now()
        candidate["acceptance"] = {
            "deployment_request_id": request_id,
            "deployment_id": deployment,
            "health_request_id": health_id,
            "result": normalized_result,
            "head_sha": head,
            "recorded_at": now.isoformat(),
        }
        if normalized_result not in EVIDENCE_SUCCESS:
            candidate["state"] = "decision_required"
            item["state"] = "decision_required"
            item["promotion_state"] = "released_after_acceptance_failure"
            _release_promotion_lease_unlocked(workstream)
        else:
            candidate["state"] = "pre_merge"
            item["state"] = "pre_merge"
            item["promotion_state"] = "pre_merge"
            item["lock_expires_at"] = (now + timedelta(minutes=LOCK_TTL_MAX_MINUTES)).isoformat()
        candidate["updated_at"] = now.isoformat()
        item["updated_at"] = now.isoformat()
        _atomic_json(path, item)
        return candidate


def complete_workstream(
    workstream_id: str,
    outcome: str,
    candidate_id: str | None = None,
    head_sha: str | None = None,
    merge_sha: str | None = None,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    normalized_outcome = validate_identifier(outcome, "outcome")
    if normalized_outcome not in WORKSTREAM_FINAL_STATES:
        raise ValueError("Workstream outcome must be merged, closed, superseded or cancelled.")
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        now = _now()
        if normalized_outcome == "merged" and _is_v2(item):
            if not candidate_id or not head_sha:
                raise ValueError("Merged completion requires exact candidate_id and head_sha.")
            candidate_key = validate_identifier(candidate_id, "candidate_id")
            head = validate_commit(head_sha)
            candidate = (item.get("candidates") or {}).get(candidate_key)
            if not isinstance(candidate, dict) or candidate.get("head_sha") != head or candidate.get("state") != "pre_merge":
                raise ValueError("Only an exact pre-merge accepted candidate may complete as merged.")
            candidate["state"] = "merged"
            candidate["updated_at"] = now.isoformat()
            if merge_sha:
                candidate["merge_sha"] = validate_commit(merge_sha)
        item["state"] = normalized_outcome
        item["promotion_state"] = "completed"
        item["completed_at"] = now.isoformat()
        item["updated_at"] = now.isoformat()
        _release_promotion_lease_unlocked(workstream)
        _atomic_json(path, item)
        return item


def reconcile_external_workstream_state(
    workstream_id: str,
    pull_request_state: str,
    pull_request_head_sha: str,
    current_main_sha: str | None = None,
    merge_sha: str | None = None,
    base_sha: str | None = None,
) -> dict[str, Any]:
    workstream = validate_identifier(workstream_id, "workstream_id")
    pr_state = validate_identifier(str(pull_request_state).lower(), "pull_request_state")
    if pr_state not in {"open", "closed", "merged"}:
        raise ValueError("pull_request_state must be open, closed or merged.")
    head = validate_commit(pull_request_head_sha)
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        if not _is_v2(item):
            raise ValueError("External reconciliation requires a V2 workstream.")
        if item.get("commit_sha") != head:
            candidate = _upsert_candidate_unlocked(item, head, base_sha=base_sha, pull_request=item.get("pull_request"), current_main_sha=current_main_sha)
            candidate["state"] = "developing"
        elif current_main_sha:
            item["current_main_sha"] = validate_commit(current_main_sha)
        item["external_state"] = {
            "pull_request_state": pr_state,
            "pull_request_head_sha": head,
            "current_main_sha": validate_commit(current_main_sha) if current_main_sha else None,
            "merge_sha": validate_commit(merge_sha) if merge_sha else None,
            "reconciled_at": _now().isoformat(),
        }
        if pr_state == "closed" and not merge_sha and item.get("state") not in WORKSTREAM_FINAL_STATES:
            item["state"] = "decision_required"
            item["decision_reason"] = "pull_request_closed_without_recorded_merge"
            _release_promotion_lease_unlocked(workstream)
        if pr_state == "merged" and item.get("state") == "pre_merge":
            current_id = item.get("current_candidate_id")
            candidate = (item.get("candidates") or {}).get(current_id)
            if isinstance(candidate, dict) and candidate.get("head_sha") == head:
                candidate["state"] = "merged"
                if merge_sha:
                    candidate["merge_sha"] = validate_commit(merge_sha)
                item["state"] = "merged"
                item["promotion_state"] = "completed"
                item["completed_at"] = _now().isoformat()
                _release_promotion_lease_unlocked(workstream)
        item["updated_at"] = _now().isoformat()
        _atomic_json(path, item)
        return item


def acquire_live_test_lease(
    live_test_scope: str,
    workstream_id: str,
    candidate_id: str,
    ttl_minutes: int = 60,
) -> dict[str, Any]:
    scope = validate_identifier(live_test_scope, "live_test_scope")
    workstream = validate_identifier(workstream_id, "workstream_id")
    candidate_key = validate_identifier(candidate_id, "candidate_id")
    ttl = int(ttl_minutes)
    if not LOCK_TTL_MINUTES <= ttl <= LOCK_TTL_MAX_MINUTES:
        raise ValueError("live-test lease duration is outside the supported range.")
    with _coordinator_mutation_lock():
        path = WORKSTREAMS / f"{workstream}.json"
        if not path.exists():
            raise ValueError("Unknown workstream_id.")
        item = _read_json(path)
        candidate = (item.get("candidates") or {}).get(candidate_key)
        if not isinstance(candidate, dict) or item.get("current_candidate_id") != candidate_key:
            raise ValueError("Live-test lease requires the current candidate.")
        LIVE_TEST_LEASES.mkdir(parents=True, exist_ok=True)
        lease_path = LIVE_TEST_LEASES / f"{scope}.json"
        if lease_path.exists():
            try:
                current = _read_json(lease_path)
                expiry = _parse_time(current.get("expires_at"))
                if expiry and expiry > _now() and current.get("workstream_id") != workstream:
                    raise ValueError("Another workstream currently holds this live-test lease.")
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass
        now = _now()
        lease = {
            "schema": "pdp-one.live-test-lease.v1",
            "live_test_scope": scope,
            "workstream_id": workstream,
            "candidate_id": candidate_key,
            "head_sha": candidate.get("head_sha"),
            "acquired_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
        }
        _atomic_json(lease_path, lease)
        return lease


def release_live_test_lease(live_test_scope: str, workstream_id: str) -> dict[str, Any]:
    scope = validate_identifier(live_test_scope, "live_test_scope")
    workstream = validate_identifier(workstream_id, "workstream_id")
    with _coordinator_mutation_lock():
        lease_path = LIVE_TEST_LEASES / f"{scope}.json"
        if not lease_path.exists():
            return {"released": False, "reason": "not_found"}
        lease = _read_json(lease_path)
        if lease.get("workstream_id") != workstream:
            raise ValueError("Live-test lease belongs to another workstream.")
        lease_path.unlink(missing_ok=True)
        return {"released": True, "live_test_scope": scope, "workstream_id": workstream}


def _visible_live_test_leases_unlocked() -> list[dict[str, Any]]:
    now = _now()
    result = []
    if not LIVE_TEST_LEASES.exists():
        return result
    for path in LIVE_TEST_LEASES.glob("*.json"):
        try:
            lease = _read_json(path)
            expiry = _parse_time(lease.get("expires_at"))
            if not expiry or expiry <= now:
                path.unlink(missing_ok=True)
                continue
            result.append(lease)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return sorted(result, key=lambda value: str(value.get("live_test_scope", "")))


def coordinator_status() -> dict[str, Any]:
    deployment_queue._require_queue()
    with _coordinator_mutation_lock():
        _reconcile_history_unlocked()
        _renew_lifecycle_leases_unlocked()
        _dispatch_next_unlocked()
        now = _now()
        raw = _load_workstreams()
        workstreams = []
        for item in raw:
            visible = dict(item)
            visible["conflicts"] = _conflicts_for_item(item, raw)
            if _is_v2(item):
                visible["dependency_blockers"] = _dependency_blockers(item, raw)
                current_id = visible.get("current_candidate_id")
                candidate = (visible.get("candidates") or {}).get(current_id)
                if isinstance(candidate, dict):
                    candidate["evidence_state"] = _candidate_evidence_state(candidate)
            visible["lock_expired"] = not _active(item, now)
            workstreams.append(visible)
        pending = []
        for path in sorted(PENDING.glob("*.json"), key=_pending_sort_key) if PENDING.exists() else []:
            try:
                value = _read_json(path)
                value.pop("envelope", None)
                value["effective_priority_rank"] = _effective_priority_rank(value, now)
                created = _parse_time(value.get("created_at"))
                value["age_seconds"] = int(max(0.0, (now - created).total_seconds())) if created else None
                pending.append(value)
            except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                continue
        return {
            "schema": "pdp-one.development-promotion-dashboard.v2",
            "workstreams": sorted(workstreams, key=lambda item: str(item.get("updated_at", "")), reverse=True),
            "pending_deployments": pending,
            "promotion_lease": _promotion_lease_unlocked(now),
            "live_test_leases": _visible_live_test_leases_unlocked(),
            "agent": deployment_queue.get_queue_status(),
            "parallel_development_allowed": True,
            "runtime_deployments_serialized": True,
            "promotion_serialized": True,
            "exact_candidate_evidence_required": True,
            "automatic_cross_chat_takeover": False,
            "arbitrary_shell_allowed": False,
        }


def _dispatcher_loop() -> None:
    while True:
        try:
            with _coordinator_mutation_lock():
                _reconcile_history_unlocked()
                _renew_lifecycle_leases_unlocked()
                _dispatch_next_unlocked()
                _visible_live_test_leases_unlocked()
                _promotion_lease_unlocked()
        except Exception:
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
    async def register_development_workstream(workstream_id: str, branch: str, changed_paths: list[str], surfaces: list[str], commit_sha: str | None = None, pull_request: int | None = None, lock_ttl_minutes: int = 120, origin_chat_ref: str | None = None, blocked_by: list[str] | None = None, requires: list[str] | None = None, integrates_with: list[str] | None = None, supersedes: list[str] | None = None, components: list[str] | None = None, runtime_resources: list[str] | None = None, database_resources: list[str] | None = None, live_test_scopes: list[str] | None = None, base_sha: str | None = None, current_main_sha: str | None = None, required_evidence: list[str] | None = None) -> dict:
        return register_workstream(workstream_id, branch, changed_paths, surfaces, commit_sha, pull_request, lock_ttl_minutes, origin_chat_ref, blocked_by, requires, integrates_with, supersedes, components, runtime_resources, database_resources, live_test_scopes, base_sha, current_main_sha, required_evidence)

    @mcp.tool(description="Refresh an existing workstream heartbeat or record its durable lifecycle state.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def update_development_workstream(workstream_id: str, state: str = "developing", lock_ttl_minutes: int = 120) -> dict:
        return heartbeat_workstream(workstream_id, state, lock_ttl_minutes)

    @mcp.tool(description="Register one exact candidate under a stable workstream. A new head makes the previous candidate evidence stale instead of reusing it.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def register_workstream_candidate(workstream_id: str, commit_sha: str, base_sha: str, pull_request: int | None = None, current_main_sha: str | None = None, required_evidence: list[str] | None = None) -> dict:
        return register_candidate(workstream_id, commit_sha, base_sha, pull_request, current_main_sha, required_evidence)

    @mcp.tool(description="Record exact-head CI, image, health or other candidate evidence. Evidence cannot be attributed to a different head SHA.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def record_workstream_candidate_evidence(workstream_id: str, candidate_id: str, evidence_kind: str, evidence_id: str, result: str, head_sha: str, details_ref: str | None = None) -> dict:
        return record_candidate_evidence(workstream_id, candidate_id, evidence_kind, evidence_id, result, head_sha, details_ref)

    @mcp.tool(description="Record an explicit owner-requested continuation from one chat reference to another while preserving the original workstream origin.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def record_development_workstream_handoff(workstream_id: str, from_chat_ref: str, to_chat_ref: str, owner_requested: bool = False) -> dict:
        return record_workstream_handoff(workstream_id, from_chat_ref, to_chat_ref, owner_requested)

    @mcp.tool(description="Reserve the single promotion lane for a candidate integrated exactly on the supplied current main. Active conflicts and dependencies fail closed.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def reserve_development_promotion(workstream_id: str, candidate_id: str, head_sha: str, current_main_sha: str, lease_minutes: int = 120) -> dict:
        return reserve_promotion(workstream_id, candidate_id, head_sha, current_main_sha, lease_minutes)

    @mcp.tool(description="Queue one exact tested commit for durable, priority-aware, serialized deployment. V2 candidates require their promotion lease and exact evidence passport.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def queue_coordinated_deployment(workstream_id: str, commit_sha: str, deployment_id: str, preview_id: str, priority: str = "normal", compatibility_key: str = "application", migration_sensitive: bool = False, destructive: bool = False, contains_commits: list[str] | None = None, candidate_id: str | None = None, current_main_sha: str | None = None, allow_redeploy: bool = False) -> dict:
        return queue_exact_deployment(workstream_id, commit_sha, deployment_id, preview_id, priority, compatibility_key, migration_sensitive, destructive, contains_commits, candidate_id, current_main_sha, allow_redeploy)

    @mcp.tool(description="Bind deployment and independent health evidence to the exact candidate and move it to PRE-MERGE only when identities match.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def record_development_candidate_acceptance(workstream_id: str, candidate_id: str, head_sha: str, deployment_request_id: str, deployment_id: str, health_request_id: str, result: str) -> dict:
        return record_candidate_acceptance(workstream_id, candidate_id, head_sha, deployment_request_id, deployment_id, health_request_id, result)

    @mcp.tool(description="Reconcile a workstream with authoritative PR/head/main facts supplied after a fresh GitHub read. Head changes invalidate prior current-candidate evidence.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def reconcile_development_workstream(workstream_id: str, pull_request_state: str, pull_request_head_sha: str, current_main_sha: str | None = None, merge_sha: str | None = None, base_sha: str | None = None) -> dict:
        return reconcile_external_workstream_state(workstream_id, pull_request_state, pull_request_head_sha, current_main_sha, merge_sha, base_sha)

    @mcp.tool(description="Complete a workstream after exact acceptance. A merged V2 workstream must reference the exact PRE-MERGE candidate.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def complete_development_workstream(workstream_id: str, outcome: str, candidate_id: str | None = None, head_sha: str | None = None, merge_sha: str | None = None) -> dict:
        return complete_workstream(workstream_id, outcome, candidate_id, head_sha, merge_sha)

    @mcp.tool(description="Acquire a source-specific live-test lease so concurrent chats do not contaminate the same external source acceptance run.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def acquire_development_live_test_lease(live_test_scope: str, workstream_id: str, candidate_id: str, ttl_minutes: int = 60) -> dict:
        return acquire_live_test_lease(live_test_scope, workstream_id, candidate_id, ttl_minutes)

    @mcp.tool(description="Release a source-specific live-test lease owned by the workstream.", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def release_development_live_test_lease(live_test_scope: str, workstream_id: str) -> dict:
        return release_live_test_lease(live_test_scope, workstream_id)

    @mcp.tool(description="Return the durable multi-chat workstream and promotion dashboard, including dynamic conflicts, dependencies, exact evidence, queue priority and Agent health.", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True))
    async def get_development_coordination_status() -> dict:
        return coordinator_status()
