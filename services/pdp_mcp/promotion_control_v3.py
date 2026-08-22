"""Non-bypassable durable promotion control for PDP One parallel development.

V3 deliberately lives below the MCP tool schema. Legacy Connected App tools and
new coordinator tools therefore share the same final-promotion lane even when a
chat has a stale tool catalogue.

Only public-safe identifiers are persisted. No shell text, secrets, private
Control data, or arbitrary commands are accepted here.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import deployment_queue

REVISION = "pdp-one.parallel-promotion-control.v3"
REPOSITORY = os.getenv("PDP_APPLICATION_REPOSITORY", "PDP-WEBBASE/PDP-One").strip()
GITHUB_API = os.getenv("PDP_APPLICATION_GITHUB_API", "https://api.github.com").rstrip("/")
GITHUB_READ_TOKEN = os.getenv("PDP_APPLICATION_GITHUB_READ_TOKEN", "").strip()
GITHUB_TIMEOUT_SECONDS = max(2, min(20, int(os.getenv("PDP_PROMOTION_GITHUB_TIMEOUT_SECONDS", "7"))))
ATTESTATION_CACHE_SECONDS = max(15, min(600, int(os.getenv("PDP_PROMOTION_ATTESTATION_CACHE_SECONDS", "90"))))
DISPATCH_POLL_SECONDS = max(2, min(60, int(os.getenv("PDP_PROMOTION_POLL_SECONDS", "5"))))
ACTIVE_LEASE_HOURS = max(2, min(72, int(os.getenv("PDP_PROMOTION_ACTIVE_LEASE_HOURS", "24"))))

DEPLOY_ACTIONS = {"deploy_approved_release", "promote_exact_candidate"}
HEALTH_ACTION = "check_deployment_health"
FINAL_TICKET_STATES = {"merged", "failed", "superseded", "cancelled", "stale_main"}
BLOCKING_TICKET_STATES = {
    "dispatching",
    "deploying",
    "acceptance",
    "health_pending",
    "pre_merge",
    "decision_required",
}
FORWARD_DEPLOY_SUCCESS_STATES = {"acceptance", "pre_merge", "merged"}
EVIDENCE_WORKFLOWS = {
    "boundary": "PDP One Application Boundary Governance",
    "verify": "PDP One CI",
    "images": "Build immutable PDP One images",
}
IMAGE_IGNORED_PREFIXES = (".github/", "docs/", "scripts/windows/", "tests/")

_started = False
_start_guard = threading.Lock()
_process_guard = threading.RLock()
_last_background_error: str | None = None
_configured_queue_root: Path | None = None


class PromotionAttestationError(RuntimeError):
    """A candidate cannot enter final promotion with authoritative evidence."""


def configure_queue_root(queue_root: Path | str) -> None:
    """Derive V3 durable paths from the queue root currently used by the caller."""
    global ROOT, READY, REQUESTS, HISTORY, ATTESTATIONS, ACTIVE, LOCK, SHARED_PROMOTION_LEASE, _configured_queue_root
    root = Path(queue_root)
    if _configured_queue_root == root:
        return
    ROOT = root / "promotion-v3"
    READY = ROOT / "ready"
    REQUESTS = ROOT / "requests"
    HISTORY = ROOT / "history"
    ATTESTATIONS = ROOT / "attestations"
    ACTIVE = ROOT / "active-ticket.json"
    LOCK = ROOT / ".mutation-lock"
    SHARED_PROMOTION_LEASE = root / "coordinator" / "promotion-lease.json"
    _configured_queue_root = root


configure_queue_root(deployment_queue.QUEUE_ROOT)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".promotion-v3-", suffix=".tmp", dir=path.parent)
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
        raise ValueError("Promotion record must be a JSON object.")
    return value


@contextmanager
def _mutation_lock(timeout_seconds: int = 5):
    """Cross-thread/process lock; callers must not recursively acquire the file lock."""
    with _process_guard:
        ROOT.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(1, timeout_seconds)
        while True:
            try:
                LOCK.mkdir()
                break
            except FileExistsError:
                try:
                    age = max(0.0, time.time() - LOCK.stat().st_mtime)
                    if age > 30:
                        LOCK.rmdir()
                        continue
                except (FileNotFoundError, OSError):
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("Promotion control is busy; retry after a fresh coordination read.")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                LOCK.rmdir()
            except FileNotFoundError:
                pass


def _safe_public(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip()
    if any(ord(ch) < 32 for ch in text):
        raise ValueError("Promotion identifiers must be public-safe text.")
    return text[:limit]


def _github_json(path: str) -> Any:
    if not REPOSITORY or "/" not in REPOSITORY:
        raise PromotionAttestationError("PDP application repository identity is invalid.")
    url = f"{GITHUB_API}/repos/{REPOSITORY}/{path.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PDP-One-Promotion-Control-V3",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_READ_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_READ_TOKEN}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 404} and not GITHUB_READ_TOKEN:
            raise PromotionAttestationError(
                "Authoritative GitHub attestation is unavailable. If PDP-One is Private, configure a locally protected read-only application-repository token; promotion fails closed without it."
            ) from exc
        raise PromotionAttestationError(f"GitHub attestation failed with HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PromotionAttestationError("GitHub attestation is temporarily unreachable; promotion was not started.") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionAttestationError("GitHub attestation returned invalid JSON.") from exc


def _workflow_run_map(commit_sha: str) -> dict[str, dict[str, Any]]:
    query = urllib.parse.urlencode({"head_sha": commit_sha, "event": "pull_request", "per_page": 100})
    result = _github_json(f"actions/runs?{query}")
    runs = result.get("workflow_runs", []) if isinstance(result, dict) else []
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        name = str(run.get("name", ""))
        if name and name not in latest:
            latest[name] = run
    return latest


def _image_evidence_required(changed_files: list[str]) -> bool:
    for path in changed_files:
        normalized = path.replace("\\", "/")
        if normalized.endswith(".md"):
            continue
        if any(normalized.startswith(prefix) for prefix in IMAGE_IGNORED_PREFIXES):
            continue
        return True
    return False


def _infer_priority(changed_files: list[str]) -> tuple[str, int]:
    infrastructure_prefixes = ("services/pdp_mcp/", "scripts/windows/", "infra/", ".github/", "release/")
    if any(path.startswith(infrastructure_prefixes) for path in changed_files):
        return "infrastructure", 10
    return "normal", 50


def _attestation_cache_path(commit_sha: str) -> Path:
    return ATTESTATIONS / f"{commit_sha}.json"


def _cached_attestation(commit_sha: str) -> dict[str, Any] | None:
    path = _attestation_cache_path(commit_sha)
    if not path.exists():
        return None
    try:
        value = _read_json(path)
        checked = _parse_time(value.get("checked_at"))
        if not checked or (_now() - checked).total_seconds() > ATTESTATION_CACHE_SECONDS:
            return None
        main = _github_json("branches/main")
        main_sha = str(((main or {}).get("commit") or {}).get("sha", ""))
        if main_sha != value.get("main_sha"):
            return None
        return value
    except (OSError, ValueError, PromotionAttestationError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def attest_commit(commit_sha: str, *, allow_cache: bool = True) -> dict[str, Any]:
    """Read exact PR/main/check identities directly from GitHub; fail closed."""
    commit = deployment_queue.validate_commit(commit_sha)
    if allow_cache:
        cached = _cached_attestation(commit)
        if cached:
            return cached

    main = _github_json("branches/main")
    main_sha = deployment_queue.validate_commit(str(((main or {}).get("commit") or {}).get("sha", "")))

    pulls = _github_json(f"commits/{commit}/pulls")
    candidates = []
    for pr in pulls if isinstance(pulls, list) else []:
        if not isinstance(pr, dict) or str(pr.get("state", "")) != "open":
            continue
        head_sha = str(((pr.get("head") or {}).get("sha", ""))).lower()
        base_ref = str(((pr.get("base") or {}).get("ref", "")))
        if head_sha == commit and base_ref == "main":
            candidates.append(pr)
    if not candidates:
        raise PromotionAttestationError("Exact commit is not the head of an open PDP-One pull request targeting main.")
    candidates.sort(key=lambda item: int(item.get("number", 0)), reverse=True)
    pr = candidates[0]
    pr_number = int(pr["number"])

    compare = _github_json(f"compare/{main_sha}...{commit}")
    behind_by = int((compare or {}).get("behind_by", -1)) if isinstance(compare, dict) else -1
    if behind_by != 0:
        raise PromotionAttestationError(
            f"Candidate is behind current main {main_sha[:12]}; keep developing and integrate latest main once at its next promotion turn."
        )

    changed_files: list[str] = []
    for page in range(1, 4):
        values = _github_json(f"pulls/{pr_number}/files?per_page=100&page={page}")
        if not isinstance(values, list):
            break
        changed_files.extend(str(item.get("filename", "")) for item in values if isinstance(item, dict) and item.get("filename"))
        if len(values) < 100:
            break
    changed_files = sorted(set(changed_files))
    if not changed_files:
        raise PromotionAttestationError("Pull request has no changed files; refusing an unbound promotion.")

    required_names = [EVIDENCE_WORKFLOWS["boundary"], EVIDENCE_WORKFLOWS["verify"]]
    if _image_evidence_required(changed_files):
        required_names.append(EVIDENCE_WORKFLOWS["images"])
    runs = _workflow_run_map(commit)
    evidence: dict[str, dict[str, Any]] = {}
    for name in required_names:
        run = runs.get(name)
        if not run:
            raise PromotionAttestationError(f"Required exact-head workflow is missing: {name}.")
        if str(run.get("status", "")) != "completed" or str(run.get("conclusion", "")) != "success":
            raise PromotionAttestationError(f"Required exact-head workflow is not successful: {name}.")
        evidence[name] = {"run_id": int(run.get("id", 0)), "status": "success", "head_sha": commit}

    priority, priority_rank = _infer_priority(changed_files)
    value = {
        "schema": "pdp-one.promotion-attestation.v3",
        "repository": REPOSITORY,
        "commit_sha": commit,
        "main_sha": main_sha,
        "pull_request": pr_number,
        "changed_files": changed_files[:300],
        "required_workflows": required_names,
        "workflow_evidence": evidence,
        "priority": priority,
        "priority_rank": priority_rank,
        "checked_at": _iso(),
        "authoritative_source": "github-api",
        "read_token_used": bool(GITHUB_READ_TOKEN),
    }
    _atomic_json(_attestation_cache_path(commit), value)
    return value


def _active_ticket_unlocked() -> dict[str, Any] | None:
    if not ACTIVE.exists():
        return None
    try:
        item = _read_json(ACTIVE)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if str(item.get("state")) in FINAL_TICKET_STATES:
        return None
    return item


def _shared_lease_unlocked() -> dict[str, Any] | None:
    if not SHARED_PROMOTION_LEASE.exists():
        return None
    try:
        lease = _read_json(SHARED_PROMOTION_LEASE)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    expiry = _parse_time(lease.get("expires_at"))
    if expiry and expiry <= _now():
        SHARED_PROMOTION_LEASE.unlink(missing_ok=True)
        return None
    return lease


def _write_shared_lease_unlocked(ticket: dict[str, Any]) -> None:
    now = _now()
    pr = int(ticket.get("pull_request") or 0)
    lease = {
        "schema": "pdp-one.promotion-lease.v3",
        "workstream_id": f"v3-pr-{pr or ticket['commit_sha'][:8]}",
        "candidate_id": f"v3-{ticket['commit_sha'][:12]}",
        "head_sha": ticket["commit_sha"],
        "base_sha": ticket["main_sha"],
        "current_main_sha": ticket["main_sha"],
        "acquired_at": ticket.get("activated_at") or now.isoformat(),
        "expires_at": (now + timedelta(hours=ACTIVE_LEASE_HOURS)).isoformat(),
        "durable_ticket_id": ticket["ticket_id"],
    }
    _atomic_json(SHARED_PROMOTION_LEASE, lease)


def _release_shared_lease_unlocked(ticket: dict[str, Any]) -> None:
    lease = _shared_lease_unlocked()
    if lease and lease.get("durable_ticket_id") == ticket.get("ticket_id"):
        SHARED_PROMOTION_LEASE.unlink(missing_ok=True)


def _agent_busy() -> bool:
    for name in ("incoming", "processing"):
        root = deployment_queue.QUEUE_ROOT / name
        if root.exists() and any(root.glob("*.json")):
            return True
    return False


def _request_path(request_id: str) -> Path:
    return REQUESTS / f"{request_id}.json"


def _ready_path(record: dict[str, Any]) -> Path:
    timestamp = record["created_at"].replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return READY / f"{int(record.get('priority_rank', 50)):02d}-{timestamp}-{record['client_request_id']}.json"


def _new_request_record(action: str, params: dict[str, Any], attestation: dict[str, Any]) -> dict[str, Any]:
    client_id = str(uuid.uuid4())
    commit = deployment_queue.validate_commit(str(params.get("commit_sha", "")))
    deployment_id = deployment_queue.validate_identifier(str(params.get("deployment_id", "")), "deployment_id")
    preview_id = deployment_queue.validate_identifier(str(params.get("preview_id", "")), "preview_id")
    now = _iso()
    return {
        "schema": "pdp-one.promotion-request.v3",
        "client_request_id": client_id,
        "action": action,
        "commit_sha": commit,
        "deployment_id": deployment_id,
        "preview_id": preview_id,
        "pull_request": int(attestation["pull_request"]),
        "main_sha": attestation["main_sha"],
        "priority": attestation.get("priority", "normal"),
        "priority_rank": int(attestation.get("priority_rank", 50)),
        "attestation": attestation,
        "state": "ready",
        "created_at": now,
        "updated_at": now,
        "agent_request_id": None,
    }


def _same_candidate(record: dict[str, Any], action: str, params: dict[str, Any]) -> bool:
    return (
        record.get("action") == action
        and record.get("commit_sha") == str(params.get("commit_sha", "")).lower()
        and record.get("deployment_id") == str(params.get("deployment_id", ""))
    )


def _find_existing_request_unlocked(action: str, params: dict[str, Any]) -> dict[str, Any] | None:
    active = _active_ticket_unlocked()
    if active and _same_candidate(active, action, params):
        request_id = active.get("client_request_id")
        path = _request_path(str(request_id))
        if request_id and path.exists():
            return _read_json(path)
    if READY.exists():
        for path in READY.glob("*.json"):
            try:
                item = _read_json(path)
                if _same_candidate(item, action, params) and item.get("state") not in {"superseded", "cancelled"}:
                    return item
            except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                continue
    return None


def _activate_unlocked(record: dict[str, Any]) -> dict[str, Any]:
    now = _iso()
    ticket = dict(record)
    ticket.update(schema="pdp-one.promotion-ticket.v3", ticket_id=str(uuid.uuid4()), state="dispatching", activated_at=now, updated_at=now)
    _atomic_json(ACTIVE, ticket)
    record.update(state="dispatching", ticket_id=ticket["ticket_id"], updated_at=now)
    _atomic_json(_request_path(record["client_request_id"]), record)
    _write_shared_lease_unlocked(ticket)
    return ticket


def _public_request_status_unlocked(request_id: str) -> dict[str, Any]:
    path = _request_path(request_id)
    if not path.exists():
        return {"request_id": request_id, "status": "pending"}
    record = _read_json(path)
    state = str(record.get("state", "pending"))
    status = "pending"
    if state in {"merged", "succeeded", "pre_merge"}:
        status = "succeeded"
    elif state == "failed":
        status = "failed"
    result = {
        "request_id": request_id,
        "status": status,
        "promotion_managed": True,
        "promotion_state": state,
        "exact_commit": record.get("commit_sha"),
        "deployment_id": record.get("deployment_id"),
        "pull_request": record.get("pull_request"),
        "current_main_sha": record.get("main_sha"),
        "agent_request_id": record.get("agent_request_id"),
    }
    if record.get("waiting_reason"):
        result["waiting_reason"] = record.get("waiting_reason")
    if record.get("decision_reason"):
        result["decision_reason"] = record.get("decision_reason")
    return result


def before_enqueue(action: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Gate stable legacy deployment tools before a signed Agent request exists."""
    configure_queue_root(deployment_queue.QUEUE_ROOT)
    if action not in DEPLOY_ACTIONS and action != HEALTH_ACTION:
        return None

    # Generic health remains a legacy diagnostic. It cannot advance acceptance
    # unless an exact active deployment id is supplied.
    if action == HEALTH_ACTION and not ACTIVE.exists():
        return None
    ensure_started()

    if action == HEALTH_ACTION:
        deployment_id = str(params.get("deployment_id", "")).strip()
        with _mutation_lock():
            active = _active_ticket_unlocked()
            if not active or not deployment_id or active.get("deployment_id") != deployment_id:
                return None
            health_client = str(uuid.uuid4())
            record = {
                "schema": "pdp-one.promotion-health-request.v3",
                "client_request_id": health_client,
                "action": action,
                "deployment_id": deployment_id,
                "commit_sha": active["commit_sha"],
                "ticket_id": active["ticket_id"],
                "state": "dispatching",
                "created_at": _iso(),
                "updated_at": _iso(),
                "agent_request_id": None,
            }
            _atomic_json(_request_path(health_client), record)
            active["state"] = "health_pending"
            active["health_client_request_id"] = health_client
            active["updated_at"] = _iso()
            _atomic_json(ACTIVE, active)
            _write_shared_lease_unlocked(active)
            return {"managed": True, "kind": "health", "client_request_id": health_client}

    commit = deployment_queue.validate_commit(str(params.get("commit_sha", "")))
    deployment_queue.validate_identifier(str(params.get("deployment_id", "")), "deployment_id")
    deployment_queue.validate_identifier(str(params.get("preview_id", "")), "preview_id")
    attestation = attest_commit(commit, allow_cache=True)

    with _mutation_lock():
        existing = _find_existing_request_unlocked(action, params)
        if existing:
            return {"managed": True, "defer": True, "response": _public_request_status_unlocked(existing["client_request_id"])}

        record = _new_request_record(action, params, attestation)
        _atomic_json(_request_path(record["client_request_id"]), record)

        active = _active_ticket_unlocked()
        shared = _shared_lease_unlocked()
        if active or shared or _agent_busy():
            record["state"] = "waiting_promotion"
            if active:
                record["waiting_reason"] = "active_v3_ticket"
            elif shared:
                record["waiting_reason"] = "active_v2_promotion_lease"
            else:
                record["waiting_reason"] = "deployment_agent_busy"
            record["updated_at"] = _iso()
            _atomic_json(_request_path(record["client_request_id"]), record)
            _atomic_json(_ready_path(record), record)
            return {"managed": True, "defer": True, "response": _public_request_status_unlocked(record["client_request_id"])}

        _activate_unlocked(record)
        return {"managed": True, "kind": "deployment", "client_request_id": record["client_request_id"]}


def after_enqueue(action: str, params: dict[str, Any], agent_request_id: str, context: dict[str, Any] | None) -> None:
    if not context or not context.get("managed"):
        return
    client_id = str(context.get("client_request_id", ""))
    if not client_id:
        return
    with _mutation_lock():
        path = _request_path(client_id)
        if not path.exists():
            return
        record = _read_json(path)
        record["agent_request_id"] = str(agent_request_id)
        record["state"] = "deploying" if action in DEPLOY_ACTIONS else "health_pending"
        record["updated_at"] = _iso()
        _atomic_json(path, record)
        active = _active_ticket_unlocked()
        if active and active.get("ticket_id") == record.get("ticket_id"):
            if action in DEPLOY_ACTIONS:
                active["agent_request_id"] = str(agent_request_id)
                active["state"] = "deploying"
            elif action == HEALTH_ACTION:
                active["health_agent_request_id"] = str(agent_request_id)
                active["state"] = "health_pending"
            active["updated_at"] = _iso()
            _atomic_json(ACTIVE, active)
            _write_shared_lease_unlocked(active)


def _find_request_by_agent_unlocked(agent_request_id: str) -> dict[str, Any] | None:
    if not REQUESTS.exists():
        return None
    for path in REQUESTS.glob("*.json"):
        try:
            record = _read_json(path)
            if record.get("agent_request_id") == agent_request_id:
                return record
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return None


def resolve_request_id(request_id: str) -> dict[str, Any] | None:
    configure_queue_root(deployment_queue.QUEUE_ROOT)
    if not ROOT.exists():
        return None
    ensure_started()
    with _mutation_lock():
        direct = _request_path(request_id)
        if direct.exists():
            record = _read_json(direct)
            return {"client_request_id": request_id, "agent_request_id": record.get("agent_request_id"), "state": record.get("state"), "managed": True, "record": record}
        record = _find_request_by_agent_unlocked(request_id)
        if record:
            return {"client_request_id": record["client_request_id"], "agent_request_id": request_id, "state": record.get("state"), "managed": True, "record": record}
    return None


def public_request_status(request_id: str) -> dict[str, Any]:
    try:
        normalized = str(uuid.UUID(str(request_id)))
    except ValueError as exc:
        raise ValueError("request_id is invalid.") from exc
    with _mutation_lock():
        return _public_request_status_unlocked(normalized)


def observe_response(client_request_id: str, agent_request_id: str, response: dict[str, Any]) -> None:
    """Advance ticket states monotonically from signed Agent responses."""
    with _mutation_lock():
        request_path = _request_path(client_request_id)
        if not request_path.exists():
            return
        record = _read_json(request_path)
        status = str(response.get("status", "pending"))
        if status not in {"succeeded", "failed"}:
            return
        record_state = str(record.get("state", ""))
        if record.get("action") in DEPLOY_ACTIONS and status == "succeeded" and record_state in FORWARD_DEPLOY_SUCCESS_STATES:
            # The same immutable Agent response may be read repeatedly. Never
            # move an already accepted/pre-merge ticket backwards.
            return
        now = _iso()
        record["agent_request_id"] = agent_request_id
        record["terminal_status"] = status
        record["updated_at"] = now
        active = _active_ticket_unlocked()

        if record.get("action") in DEPLOY_ACTIONS:
            if status == "failed":
                record["state"] = "failed"
                _atomic_json(request_path, record)
                if active and active.get("ticket_id") == record.get("ticket_id"):
                    active["state"] = "failed"
                    active["decision_reason"] = "deployment_failed"
                    active["updated_at"] = now
                    _archive_active_unlocked(active)
                return
            runtime_accepted = bool(response.get("runtime_accepted"))
            record["state"] = "pre_merge" if runtime_accepted else "acceptance"
            _atomic_json(request_path, record)
            if active and active.get("ticket_id") == record.get("ticket_id"):
                if str(active.get("state")) == "pre_merge":
                    return
                active["state"] = record["state"]
                active["deployment_completed_at"] = now
                active["updated_at"] = now
                if runtime_accepted:
                    active["runtime_accepted"] = True
                    active["acceptance_source"] = "composite_promote_exact_candidate"
                _atomic_json(ACTIVE, active)
                _write_shared_lease_unlocked(active)
            return

        if record.get("action") == HEALTH_ACTION:
            if not active or active.get("ticket_id") != record.get("ticket_id"):
                record["state"] = "failed" if status == "failed" else "succeeded"
                _atomic_json(request_path, record)
                return
            if status == "succeeded":
                record["state"] = "succeeded"
                active["state"] = "pre_merge"
                active["runtime_accepted"] = True
                active["health_completed_at"] = now
                active["health_agent_request_id"] = agent_request_id
                active["updated_at"] = now
            else:
                record["state"] = "failed"
                active["state"] = "decision_required"
                active["decision_reason"] = "independent_health_failed"
                active["updated_at"] = now
            _atomic_json(request_path, record)
            _atomic_json(ACTIVE, active)
            _write_shared_lease_unlocked(active)


def _archive_active_unlocked(ticket: dict[str, Any]) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    ticket["completed_at"] = ticket.get("completed_at") or _iso()
    _atomic_json(HISTORY / f"{ticket['ticket_id']}.json", ticket)
    _release_shared_lease_unlocked(ticket)
    ACTIVE.unlink(missing_ok=True)


def _ready_records_unlocked() -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    if not READY.exists():
        return result
    now = _now()
    for path in READY.glob("*.json"):
        try:
            record = _read_json(path)
            created = _parse_time(record.get("created_at")) or now
            hours = max(0, int((now - created).total_seconds() // 3600))
            record["effective_priority_rank"] = max(0, int(record.get("priority_rank", 50)) - min(30, (hours // 6) * 5))
            result.append((path, record))
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return sorted(result, key=lambda pair: (int(pair[1].get("effective_priority_rank", 50)), str(pair[1].get("created_at", ""))))


def _dispatch_waiting_candidate() -> None:
    with _mutation_lock():
        if _active_ticket_unlocked() or _shared_lease_unlocked() or _agent_busy():
            return
        records = _ready_records_unlocked()
        if not records:
            return
        selected_path, selected = records[0]
        client_id = selected["client_request_id"]
        commit = selected["commit_sha"]

    try:
        attestation = attest_commit(commit, allow_cache=False)
    except PromotionAttestationError as exc:
        with _mutation_lock():
            path = _request_path(client_id)
            if path.exists():
                record = _read_json(path)
                record["state"] = "waiting_refresh"
                record["decision_reason"] = _safe_public(str(exc), 400)
                record["updated_at"] = _iso()
                _atomic_json(path, record)
            selected_path.unlink(missing_ok=True)
        return

    with _mutation_lock():
        if _active_ticket_unlocked() or _shared_lease_unlocked() or _agent_busy():
            return
        path = _request_path(client_id)
        if not path.exists():
            selected_path.unlink(missing_ok=True)
            return
        record = _read_json(path)
        record["attestation"] = attestation
        record["main_sha"] = attestation["main_sha"]
        record["pull_request"] = int(attestation["pull_request"])
        ticket = _activate_unlocked(record)
        selected_path.unlink(missing_ok=True)
        context = {"managed": True, "kind": "deployment", "client_request_id": client_id}

    try:
        deployment_queue.enqueue(
            record["action"],
            {"commit_sha": record["commit_sha"], "deployment_id": record["deployment_id"], "preview_id": record["preview_id"]},
            _promotion_internal=True,
            _promotion_context=context,
        )
    except Exception as exc:
        with _mutation_lock():
            active = _active_ticket_unlocked()
            if active and active.get("ticket_id") == ticket.get("ticket_id"):
                active["state"] = "decision_required"
                active["decision_reason"] = f"scheduler_dispatch_failed:{type(exc).__name__}"
                active["updated_at"] = _iso()
                _atomic_json(ACTIVE, active)
                _write_shared_lease_unlocked(active)


def _reconcile_active_github() -> None:
    with _mutation_lock():
        active = _active_ticket_unlocked()
        if not active:
            return
        _write_shared_lease_unlocked(active)
        state = str(active.get("state", ""))
        pr_number = int(active.get("pull_request") or 0)
        commit = str(active.get("commit_sha", ""))
        ticket_id = str(active.get("ticket_id", ""))
    if not pr_number or not commit:
        return
    try:
        pr = _github_json(f"pulls/{pr_number}")
        main = _github_json("branches/main")
    except PromotionAttestationError:
        return
    main_sha = str(((main or {}).get("commit") or {}).get("sha", ""))
    merged = bool((pr or {}).get("merged"))
    pr_state = str((pr or {}).get("state", ""))
    pr_head = str((((pr or {}).get("head") or {}).get("sha", ""))).lower()

    with _mutation_lock():
        current = _active_ticket_unlocked()
        if not current or current.get("ticket_id") != ticket_id:
            return
        if merged and pr_head == commit:
            current["state"] = "merged"
            current["merge_sha"] = str((pr or {}).get("merge_commit_sha") or main_sha)
            current["completed_at"] = _iso()
            current["updated_at"] = _iso()
            request_path = _request_path(current["client_request_id"])
            if request_path.exists():
                record = _read_json(request_path)
                record["state"] = "merged"
                record["updated_at"] = _iso()
                _atomic_json(request_path, record)
            _archive_active_unlocked(current)
            return
        if pr_state == "closed" and not merged:
            current["state"] = "cancelled"
            current["decision_reason"] = "pull_request_closed_without_merge"
            current["updated_at"] = _iso()
            _archive_active_unlocked(current)
            return
        if state in BLOCKING_TICKET_STATES and main_sha and main_sha != current.get("main_sha"):
            current["state"] = "stale_main"
            current["decision_reason"] = "main_advanced_during_active_promotion"
            current["observed_new_main_sha"] = main_sha
            current["updated_at"] = _iso()
            _archive_active_unlocked(current)


def status_snapshot() -> dict[str, Any]:
    configure_queue_root(deployment_queue.QUEUE_ROOT)
    ensure_started()
    with _mutation_lock():
        active = _active_ticket_unlocked()
        ready = _ready_records_unlocked()
        visible_active = None
        if active:
            visible_active = {
                "ticket_id": active.get("ticket_id"),
                "state": active.get("state"),
                "pull_request": active.get("pull_request"),
                "commit_sha": active.get("commit_sha"),
                "main_sha": active.get("main_sha"),
                "deployment_id": active.get("deployment_id"),
                "client_request_id": active.get("client_request_id"),
                "agent_request_id": active.get("agent_request_id"),
                "runtime_accepted": bool(active.get("runtime_accepted", False)),
                "decision_reason": active.get("decision_reason"),
                "updated_at": active.get("updated_at"),
            }
        waiting_states: dict[str, int] = {}
        for _, record in ready:
            state = str(record.get("state", "waiting_promotion"))
            waiting_states[state] = waiting_states.get(state, 0) + 1
        return {
            "revision": REVISION,
            "legacy_deploy_bypass_allowed": False,
            "single_final_promotion_lane": True,
            "durable_ticket_across_chat_lifetime": True,
            "authoritative_github_attestation": True,
            "github_read_token_configured": bool(GITHUB_READ_TOKEN),
            "active_ticket": visible_active,
            "ready_count": len(ready),
            "ready_states": waiting_states,
            "shared_promotion_lease_present": bool(_shared_lease_unlocked()),
            "background_error": _last_background_error,
        }


def _loop() -> None:
    global _last_background_error
    while True:
        try:
            _reconcile_active_github()
            _dispatch_waiting_candidate()
            _last_background_error = None
        except Exception as exc:
            _last_background_error = type(exc).__name__
        time.sleep(DISPATCH_POLL_SECONDS)


def ensure_started() -> None:
    global _started
    configure_queue_root(deployment_queue.QUEUE_ROOT)
    with _start_guard:
        if _started:
            return
        for path in (ROOT, READY, REQUESTS, HISTORY, ATTESTATIONS):
            path.mkdir(parents=True, exist_ok=True)
        thread = threading.Thread(target=_loop, name="pdp-promotion-control-v3", daemon=True)
        thread.start()
        _started = True
