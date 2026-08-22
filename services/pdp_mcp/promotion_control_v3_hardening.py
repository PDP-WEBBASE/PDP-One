"""Targeted runtime hardening for Parallel Promotion Control V3.

This module patches only audit-proven V3 gaps while preserving the accepted
V3 durable record formats and public tool contract.
"""

from __future__ import annotations

import os
import time
from typing import Any

import deployment_queue
import promotion_control_v3 as promotion

# Reconciliation performs two public GitHub reads while a ticket is active.
# A 180-second default is about 40 reads/hour, leaving headroom below the
# normal anonymous REST budget for attestations and unrelated health work.
GITHUB_RECONCILE_SECONDS = max(
    60,
    min(600, int(os.getenv("PDP_PROMOTION_GITHUB_RECONCILE_SECONDS", "180"))),
)
ORPHAN_BINDING_SECONDS = max(
    300,
    min(3600, int(os.getenv("PDP_PROMOTION_ORPHAN_BINDING_SECONDS", "600"))),
)


_original_configure_queue_root = promotion.configure_queue_root


def configure_queue_root(queue_root) -> None:
    """Keep V3 state and the queue emergency reserve on the same durable root."""
    _original_configure_queue_root(queue_root)
    deployment_queue.RESERVE_PATH = promotion.ROOT / ".queue-emergency-reserve"


# Apply the durable path before tools/status are served. In CI, the helper
# safely declines to allocate the reserve when the queue filesystem is absent.
configure_queue_root(deployment_queue.QUEUE_ROOT)
deployment_queue._ensure_emergency_reserve()


def attest_commit(commit_sha: str, *, allow_cache: bool = True) -> dict[str, Any]:
    """Attest exact candidate using the effective current-main -> head diff."""
    commit = deployment_queue.validate_commit(commit_sha)
    if allow_cache:
        cached = promotion._cached_attestation(commit)
        if cached:
            return cached

    main = promotion._github_json("branches/main")
    main_sha = deployment_queue.validate_commit(str(((main or {}).get("commit") or {}).get("sha", "")))

    pulls = promotion._github_json(f"commits/{commit}/pulls")
    candidates = []
    for pr in pulls if isinstance(pulls, list) else []:
        if not isinstance(pr, dict) or str(pr.get("state", "")) != "open":
            continue
        head_sha = str(((pr.get("head") or {}).get("sha", ""))).lower()
        base_ref = str(((pr.get("base") or {}).get("ref", "")))
        if head_sha == commit and base_ref == "main":
            candidates.append(pr)
    if not candidates:
        raise promotion.PromotionAttestationError(
            "Exact commit is not the head of an open PDP-One pull request targeting main."
        )
    candidates.sort(key=lambda item: int(item.get("number", 0)), reverse=True)
    pr_number = int(candidates[0]["number"])

    compare = promotion._github_json(f"compare/{main_sha}...{commit}")
    if not isinstance(compare, dict):
        raise promotion.PromotionAttestationError("GitHub current-main comparison returned an invalid result.")
    behind_by = int(compare.get("behind_by", -1))
    if behind_by != 0:
        raise promotion.PromotionAttestationError(
            f"Candidate is behind current main {main_sha[:12]}; keep developing and integrate latest main once at its next promotion turn."
        )

    compare_files = compare.get("files")
    if not isinstance(compare_files, list):
        raise promotion.PromotionAttestationError(
            "GitHub current-main comparison did not provide an authoritative effective file set."
        )
    if len(compare_files) >= 300:
        raise promotion.PromotionAttestationError(
            "Effective candidate diff is too large for exact V3 file attestation; refresh a bounded candidate before promotion."
        )
    changed_files = sorted(
        {
            str(item.get("filename", ""))
            for item in compare_files
            if isinstance(item, dict) and item.get("filename")
        }
    )
    if not changed_files:
        raise promotion.PromotionAttestationError(
            "Current-main comparison has no changed files; refusing an unbound promotion."
        )

    required_names = [promotion.EVIDENCE_WORKFLOWS["boundary"], promotion.EVIDENCE_WORKFLOWS["verify"]]
    if promotion._image_evidence_required(changed_files):
        required_names.append(promotion.EVIDENCE_WORKFLOWS["images"])
    runs = promotion._workflow_run_map(commit)
    evidence: dict[str, dict[str, Any]] = {}
    for name in required_names:
        run = runs.get(name)
        if not run:
            raise promotion.PromotionAttestationError(f"Required exact-head workflow is missing: {name}.")
        if str(run.get("status", "")) != "completed" or str(run.get("conclusion", "")) != "success":
            raise promotion.PromotionAttestationError(f"Required exact-head workflow is not successful: {name}.")
        evidence[name] = {"run_id": int(run.get("id", 0)), "status": "success", "head_sha": commit}

    priority, priority_rank = promotion._infer_priority(changed_files)
    value = {
        "schema": "pdp-one.promotion-attestation.v3",
        "repository": promotion.REPOSITORY,
        "commit_sha": commit,
        "main_sha": main_sha,
        "pull_request": pr_number,
        "changed_files": changed_files,
        "changed_files_source": "current-main-compare",
        "required_workflows": required_names,
        "workflow_evidence": evidence,
        "priority": priority,
        "priority_rank": priority_rank,
        "checked_at": promotion._iso(),
        "authoritative_source": "github-api",
        "read_token_used": bool(promotion.GITHUB_READ_TOKEN),
    }
    promotion._atomic_json(promotion._attestation_cache_path(commit), value)
    return value


def _public_request_status_unlocked(request_id: str) -> dict[str, Any]:
    """Expose stale transport bindings as decision-required, never endless pending."""
    path = promotion._request_path(request_id)
    if not path.exists():
        return {"request_id": request_id, "status": "pending"}
    record = promotion._read_json(path)
    state = str(record.get("state", "pending"))
    created = promotion._parse_time(record.get("created_at"))
    if (
        state in {"dispatching", "deploying", "health_pending"}
        and not record.get("agent_request_id")
        and created
        and (promotion._now() - created).total_seconds() >= ORPHAN_BINDING_SECONDS
    ):
        record["state"] = "decision_required"
        record["decision_reason"] = "agent_request_binding_missing"
        record["updated_at"] = promotion._iso()
        promotion._atomic_json(path, record)
        active = promotion._active_ticket_unlocked()
        if active and active.get("ticket_id") == record.get("ticket_id"):
            active["state"] = "decision_required"
            active["decision_reason"] = "agent_request_binding_missing"
            active["updated_at"] = promotion._iso()
            promotion._atomic_json(promotion.ACTIVE, active)
            promotion._write_shared_lease_unlocked(active)
        state = "decision_required"

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


def publish_failed(agent_request_id: str, context: dict[str, Any] | None, reason_type: str) -> None:
    """Fail and release a V3 ticket if its signed request was never published."""
    if not context or not context.get("managed"):
        return
    client_id = str(context.get("client_request_id", ""))
    if not client_id:
        return
    with promotion._mutation_lock():
        path = promotion._request_path(client_id)
        if not path.exists():
            return
        record = promotion._read_json(path)
        record["agent_request_id"] = str(agent_request_id)
        record["terminal_status"] = "not_published"
        record["state"] = "failed"
        record["decision_reason"] = f"agent_request_publish_failed:{promotion._safe_public(reason_type, 80)}"
        record["updated_at"] = promotion._iso()
        promotion._atomic_json(path, record)
        active = promotion._active_ticket_unlocked()
        if active and active.get("ticket_id") == record.get("ticket_id"):
            active["state"] = "failed"
            active["decision_reason"] = record["decision_reason"]
            active["agent_request_id"] = str(agent_request_id)
            active["updated_at"] = promotion._iso()
            promotion._archive_active_unlocked(active)


def _loop() -> None:
    """Keep local dispatch responsive while rate-limiting GitHub reconciliation."""
    last_github_reconcile = 0.0
    while True:
        try:
            now = time.monotonic()
            if now - last_github_reconcile >= GITHUB_RECONCILE_SECONDS:
                promotion._reconcile_active_github()
                last_github_reconcile = now
            promotion._dispatch_waiting_candidate()
            promotion._last_background_error = None
        except Exception as exc:  # fail closed; visible through status_snapshot
            promotion._last_background_error = type(exc).__name__
        time.sleep(promotion.DISPATCH_POLL_SECONDS)


_original_status_snapshot = promotion.status_snapshot


def status_snapshot() -> dict[str, Any]:
    value = _original_status_snapshot()
    value["github_reconcile_interval_seconds"] = GITHUB_RECONCILE_SECONDS
    value["effective_diff_source"] = "current-main-compare"
    value["prepublish_agent_binding"] = True
    value["emergency_reserve_host_backed"] = deployment_queue.RESERVE_PATH.parent == promotion.ROOT
    return value


# Apply the hardening before the MCP server registers or serves deployment tools.
promotion.configure_queue_root = configure_queue_root
promotion.attest_commit = attest_commit
promotion._public_request_status_unlocked = _public_request_status_unlocked
promotion.publish_failed = publish_failed
promotion._loop = _loop
promotion.status_snapshot = status_snapshot
promotion.GITHUB_RECONCILE_SECONDS = GITHUB_RECONCILE_SECONDS
promotion.ORPHAN_BINDING_SECONDS = ORPHAN_BINDING_SECONDS
