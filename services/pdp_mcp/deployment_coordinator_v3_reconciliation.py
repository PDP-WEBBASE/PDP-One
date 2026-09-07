"""Fail-closed Promotion V3 -> Coordinator acceptance reconciliation.

Promotion V3 is the authoritative deployment lane for modern PDP One promotions,
while the V2 development coordinator historically accepted only deployment
records created through its own queue. This adapter reconciles an exact,
successful V3 deployment and independent health request into the coordinator's
public-safe history before retrying the existing acceptance binder.
"""

from __future__ import annotations

from typing import Any

import deployment_coordinator as coordinator
import deployment_queue
import promotion_control_v3 as promotion

_MISSING_HISTORY_ERROR = "Deployment request evidence is missing from coordinator history."
_SUCCESSFUL_TICKET_STATES = {"pre_merge", "merged"}
_ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE = coordinator.record_candidate_acceptance
_installed = False


def _promotion_request(request_id: str, expected_action: str, expected_schema: str) -> tuple[str, dict[str, Any]]:
    mapping = promotion.resolve_request_id(request_id)
    if not mapping or not mapping.get("managed"):
        raise ValueError("Promotion V3 request evidence is missing.")
    client_request_id = str(mapping.get("client_request_id") or "")
    record = mapping.get("record")
    if not client_request_id or not isinstance(record, dict):
        raise ValueError("Promotion V3 request evidence is incomplete.")
    if record.get("schema") != expected_schema or record.get("action") != expected_action:
        raise ValueError("Promotion V3 request type does not match the required evidence.")
    if record.get("client_request_id") != client_request_id:
        raise ValueError("Promotion V3 request identity is inconsistent.")
    return client_request_id, record


def _ticket_record(ticket_id: str) -> dict[str, Any]:
    active = promotion.ACTIVE
    if active.exists():
        value = promotion._read_json(active)
        if value.get("ticket_id") == ticket_id:
            return value
    history = promotion.HISTORY / f"{ticket_id}.json"
    if not history.exists():
        raise ValueError("Promotion V3 ticket evidence is missing.")
    return promotion._read_json(history)


def _validate_v3_evidence(
    deployment_request_id: str,
    health_request_id: str,
    head_sha: str,
    deployment_id: str,
) -> tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    promotion.configure_queue_root(deployment_queue.QUEUE_ROOT)
    deployment_client_id, deployment_record = _promotion_request(
        deployment_request_id,
        "promote_exact_candidate",
        "pdp-one.promotion-request.v3",
    )
    health_client_id, health_record = _promotion_request(
        health_request_id,
        "check_deployment_health",
        "pdp-one.promotion-health-request.v3",
    )

    ticket_id = str(deployment_record.get("ticket_id") or "")
    if not ticket_id or health_record.get("ticket_id") != ticket_id:
        raise ValueError("Promotion V3 deployment and health evidence do not share one exact ticket.")
    ticket = _ticket_record(ticket_id)

    for record, label in ((deployment_record, "deployment"), (health_record, "health"), (ticket, "ticket")):
        if record.get("commit_sha") != head_sha or record.get("deployment_id") != deployment_id:
            raise ValueError(f"Promotion V3 {label} evidence does not match the exact candidate.")

    if deployment_record.get("terminal_status") != "succeeded":
        raise ValueError("Promotion V3 deployment did not complete successfully.")
    if str(deployment_record.get("state")) not in _SUCCESSFUL_TICKET_STATES:
        raise ValueError("Promotion V3 deployment has not reached an accepted lifecycle state.")
    if health_record.get("terminal_status") != "succeeded" or health_record.get("state") != "succeeded":
        raise ValueError("Promotion V3 independent health did not complete successfully.")
    if ticket.get("schema") != "pdp-one.promotion-ticket.v3" or ticket.get("ticket_id") != ticket_id:
        raise ValueError("Promotion V3 ticket identity is invalid.")
    if str(ticket.get("state")) not in _SUCCESSFUL_TICKET_STATES or ticket.get("runtime_accepted") is not True:
        raise ValueError("Promotion V3 ticket is not runtime accepted.")
    if ticket.get("client_request_id") != deployment_client_id:
        raise ValueError("Promotion V3 ticket deployment lineage is inconsistent.")
    if ticket.get("health_client_request_id") != health_client_id:
        raise ValueError("Promotion V3 ticket health lineage is inconsistent.")
    if deployment_record.get("agent_request_id") and ticket.get("agent_request_id") != deployment_record.get("agent_request_id"):
        raise ValueError("Promotion V3 deployment Agent lineage is inconsistent.")
    if health_record.get("agent_request_id") and ticket.get("health_agent_request_id") != health_record.get("agent_request_id"):
        raise ValueError("Promotion V3 health Agent lineage is inconsistent.")

    return deployment_client_id, health_client_id, deployment_record, health_record, ticket


def record_candidate_acceptance_with_v3(
    workstream_id: str,
    candidate_id: str,
    head_sha: str,
    deployment_request_id: str,
    deployment_id: str,
    health_request_id: str,
    result: str,
) -> dict[str, Any]:
    try:
        return _ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE(
            workstream_id,
            candidate_id,
            head_sha,
            deployment_request_id,
            deployment_id,
            health_request_id,
            result,
        )
    except ValueError as exc:
        if str(exc) != _MISSING_HISTORY_ERROR:
            raise

    deployment_client_id, health_client_id, _deployment, _health, ticket = _validate_v3_evidence(
        deployment_request_id,
        health_request_id,
        head_sha,
        deployment_id,
    )
    history_path = coordinator.HISTORY / f"{deployment_client_id}.json"
    reconciled = {
        "schema": "pdp-one.coordinated-deployment.v2-reconciled-v3",
        "request_id": deployment_client_id,
        "workstream_id": workstream_id,
        "candidate_id": candidate_id,
        "commit_sha": head_sha,
        "deployment_id": deployment_id,
        "state": "succeeded",
        "evidence_source": "promotion-v3",
        "promotion_ticket_id": ticket["ticket_id"],
        "reconciled_at": coordinator._now().isoformat(),
    }
    coordinator._atomic_json(history_path, reconciled)
    return _ORIGINAL_RECORD_CANDIDATE_ACCEPTANCE(
        workstream_id,
        candidate_id,
        head_sha,
        deployment_client_id,
        deployment_id,
        health_client_id,
        result,
    )


def install() -> None:
    """Install once; registered MCP tool closures resolve this module global at call time."""
    global _installed
    if _installed:
        return
    coordinator.record_candidate_acceptance = record_candidate_acceptance_with_v3
    _installed = True
