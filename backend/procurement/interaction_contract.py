import hashlib
import secrets
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import AuditEvent

from .models import ProcurementCase, ProcurementNotice
from .models_interaction import (
    ProcurementChangeJournal,
    ProcurementDomainRevision,
    ProcurementOutboxEvent,
    ProcurementPendingAction,
    ProcurementWriteLease,
)

DOMAIN = "procurement"
WRITE_SCOPE = ["procurement.select_notice.v1"]
DEFAULT_LEASE_MINUTES = 60
MAX_LEASE_MINUTES = 120
PENDING_ACTION_MINUTES = 30
MAX_PENDING_CANDIDATES = 20

CAPABILITIES = {
    "schema": "pdp-one.interaction-capabilities.v1",
    "read": [
        "read.procurement.query.v1",
        "read.procurement.revision.v1",
        "read.procurement.changes.v1",
    ],
    "write": [
        "write.procurement.arm.v1",
        "write.procurement.disarm.v1",
        "write.procurement.select_notice.v1",
        "write.procurement.pending_select.v1",
    ],
    "safety": {
        "write_default": "blocked",
        "arming_keyword": "PDPONE WEB",
        "disarm_keyword": "PDPONE WEB END",
        "server_side_lease_required": True,
        "ambiguous_write_requires_confirmation": True,
        "generic_database_write": False,
        "read_after_write_verification": True,
        "audit_required": True,
        "idempotency_required": True,
    },
}


def normalize_conversation_key(value: str) -> str:
    token = str(value or "").strip()
    if not token or len(token) > 160:
        raise ValidationError({"conversation_key": "A bounded conversation key is required."})
    return token


def current_revision() -> int:
    state, _ = ProcurementDomainRevision.objects.get_or_create(domain=DOMAIN, defaults={"revision": 0})
    return state.revision


def arm_write_lease(*, user, conversation_key: str, ttl_minutes: int = DEFAULT_LEASE_MINUTES) -> dict:
    conversation_key = normalize_conversation_key(conversation_key)
    ttl_minutes = min(max(int(ttl_minutes), 5), MAX_LEASE_MINUTES)
    now = timezone.now()
    expires_at = now + timedelta(minutes=ttl_minutes)
    nonce = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()

    with transaction.atomic():
        ProcurementWriteLease.objects.filter(
            user=user,
            conversation_key=conversation_key,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).update(revoked_at=now)
        lease = ProcurementWriteLease.objects.create(
            user=user,
            conversation_key=conversation_key,
            token_hash=token_hash,
            scope=WRITE_SCOPE,
            expires_at=expires_at,
        )
        AuditEvent.objects.create(
            actor=user.username,
            action="procurement.chatgpt.write_lease.arm",
            target_type="procurement_write_lease",
            target_id=str(lease.id),
            payload={
                "conversation_key_hash": hashlib.sha256(conversation_key.encode("utf-8")).hexdigest(),
                "scope": WRITE_SCOPE,
                "expires_at": expires_at.isoformat(),
            },
        )
    return {
        "lease_id": str(lease.id),
        "write_armed": True,
        "scope": lease.scope,
        "expires_at": lease.expires_at,
    }


def disarm_write_lease(*, user, conversation_key: str) -> dict:
    conversation_key = normalize_conversation_key(conversation_key)
    now = timezone.now()
    leases = ProcurementWriteLease.objects.filter(
        user=user,
        conversation_key=conversation_key,
        revoked_at__isnull=True,
        expires_at__gt=now,
    )
    lease_ids = [str(item) for item in leases.values_list("id", flat=True)]
    leases.update(revoked_at=now)
    ProcurementPendingAction.objects.filter(
        user=user,
        conversation_key=conversation_key,
        status=ProcurementPendingAction.Status.AWAITING_CONFIRMATION,
    ).update(status=ProcurementPendingAction.Status.CANCELLED)
    AuditEvent.objects.create(
        actor=user.username,
        action="procurement.chatgpt.write_lease.disarm",
        target_type="procurement_write_lease",
        target_id=lease_ids[0] if len(lease_ids) == 1 else "",
        payload={
            "conversation_key_hash": hashlib.sha256(conversation_key.encode("utf-8")).hexdigest(),
            "revoked_count": len(lease_ids),
        },
    )
    return {"write_armed": False, "revoked_count": len(lease_ids)}


def require_write_lease(*, user, conversation_key: str, lease_id: str, capability: str) -> ProcurementWriteLease:
    conversation_key = normalize_conversation_key(conversation_key)
    try:
        parsed_id = uuid.UUID(str(lease_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("A valid PDPONE WEB write lease is required.") from exc

    now = timezone.now()
    lease = ProcurementWriteLease.objects.filter(
        id=parsed_id,
        user=user,
        conversation_key=conversation_key,
        revoked_at__isnull=True,
        expires_at__gt=now,
    ).first()
    if lease is None or capability not in set(lease.scope or []):
        raise PermissionDenied("PDPONE WEB write mode is not armed for this conversation or has expired.")
    lease.last_used_at = now
    lease.save(update_fields=["last_used_at", "updated_at"])
    return lease


def prepare_pending_select_v1(*, user, conversation_key: str, lease_id: str, candidate_notice_ids: list[str], requested_text: str = "") -> dict:
    conversation_key = normalize_conversation_key(conversation_key)
    require_write_lease(
        user=user,
        conversation_key=conversation_key,
        lease_id=lease_id,
        capability="procurement.select_notice.v1",
    )
    if not isinstance(candidate_notice_ids, list) or not 2 <= len(candidate_notice_ids) <= MAX_PENDING_CANDIDATES:
        raise ValidationError({"candidate_notice_ids": "Ambiguous confirmation requires between 2 and 20 candidate notice IDs."})
    parsed_ids = []
    for value in candidate_notice_ids:
        try:
            parsed_ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError({"candidate_notice_ids": "Every candidate must be an exact notice UUID."}) from exc
    records = list(
        ProcurementNotice.objects.filter(
            id__in=parsed_ids,
            soft_deleted_at__isnull=True,
            is_hidden=False,
        ).values("id", "resolved_notice_type", "title", "employer_name", "submission_deadline")
    )
    by_id = {str(item["id"]): item for item in records}
    ordered = [by_id[str(item)] for item in parsed_ids if str(item) in by_id]
    if len(ordered) < 2:
        raise ValidationError({"candidate_notice_ids": "At least two writable candidates must still exist."})
    expires_at = timezone.now() + timedelta(minutes=PENDING_ACTION_MINUTES)
    pending = ProcurementPendingAction.objects.create(
        user=user,
        conversation_key=conversation_key,
        command="select_notice",
        command_version=1,
        candidates=[
            {
                "notice_id": str(item["id"]),
                "notice_type": item["resolved_notice_type"],
                "title": item["title"],
                "employer_name": item["employer_name"],
                "submission_deadline": item["submission_deadline"].isoformat() if item["submission_deadline"] else None,
            }
            for item in ordered
        ],
        requested_payload={"requested_text": str(requested_text or "")[:1000]},
        expires_at=expires_at,
    )
    AuditEvent.objects.create(
        actor=user.username,
        action="procurement.command.select_notice.v1.awaiting_confirmation",
        target_type="procurement_pending_action",
        target_id=str(pending.id),
        payload={
            "candidate_notice_ids": [item["notice_id"] for item in pending.candidates],
            "expires_at": expires_at.isoformat(),
        },
    )
    return {
        "pending_action_id": str(pending.id),
        "status": pending.status,
        "command": "select_notice.v1",
        "candidates": pending.candidates,
        "expires_at": expires_at,
        "write_performed": False,
        "confirmation_required": True,
    }


def _next_revision_locked() -> int:
    state, _ = ProcurementDomainRevision.objects.select_for_update().get_or_create(
        domain=DOMAIN,
        defaults={"revision": 0},
    )
    state.revision = F("revision") + 1
    state.save(update_fields=["revision", "updated_at"])
    state.refresh_from_db(fields=["revision", "updated_at"])
    return state.revision


def _record_change(*, user, notice: ProcurementNotice, action: str, before: dict, after: dict, contexts: list[str]) -> tuple[int, uuid.UUID]:
    revision = _next_revision_locked()
    correlation_id = uuid.uuid4()
    journal = ProcurementChangeJournal.objects.create(
        domain=DOMAIN,
        revision=revision,
        entity_type="procurement_notice",
        entity_id=str(notice.id),
        action=action,
        affected_contexts=contexts,
        correlation_id=correlation_id,
        payload={"before": before, "after": after},
    )
    ProcurementOutboxEvent.objects.create(
        event_type="procurement.notice.workflow.changed",
        aggregate_type="procurement_notice",
        aggregate_id=str(notice.id),
        correlation_id=correlation_id,
        payload={
            "domain": DOMAIN,
            "revision": revision,
            "action": action,
            "notice_id": str(notice.id),
            "notice_type": notice.resolved_notice_type,
            "affected_contexts": contexts,
            "journal_id": str(journal.id),
        },
    )
    AuditEvent.objects.create(
        actor=user.username,
        action=action,
        target_type="procurement_notice",
        target_id=str(notice.id),
        payload={
            "revision": revision,
            "correlation_id": str(correlation_id),
            "before": before,
            "after": after,
            "affected_contexts": contexts,
        },
    )
    return revision, correlation_id


def select_notice_v1(*, user, conversation_key: str, lease_id: str, notice_id: str) -> dict:
    require_write_lease(
        user=user,
        conversation_key=conversation_key,
        lease_id=lease_id,
        capability="procurement.select_notice.v1",
    )
    try:
        parsed_notice_id = uuid.UUID(str(notice_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"notice_id": "An exact procurement notice UUID is required. Ambiguous writes must be confirmed first."}) from exc

    with transaction.atomic():
        notice = ProcurementNotice.objects.select_for_update().filter(
            id=parsed_notice_id,
            soft_deleted_at__isnull=True,
            is_hidden=False,
        ).first()
        if notice is None:
            raise ValidationError({"notice_id": "Procurement notice not found or is not writable."})

        existing_case = ProcurementCase.objects.select_for_update().filter(notice=notice).first()
        if existing_case is not None:
            verified = ProcurementCase.objects.filter(id=existing_case.id, notice=notice).exists()
            return {
                "command": "select_notice.v1",
                "changed": False,
                "idempotent": True,
                "notice_id": str(notice.id),
                "case_id": str(existing_case.id),
                "current_stage": existing_case.stage,
                "verified": verified,
                "verification": "existing_workflow_case",
                "revision": current_revision(),
            }

        before = {"workflow": "unselected", "case_id": None}
        case = ProcurementCase.objects.create(
            notice=notice,
            stage=ProcurementCase.Stage.SELECTED,
            created_by=user,
            protected_from_retention=True,
        )
        if not notice.retention_protected:
            ProcurementNotice.objects.filter(id=notice.id).update(retention_protected=True)
            notice.retention_protected = True
        after = {"workflow": ProcurementCase.Stage.SELECTED, "case_id": str(case.id)}
        contexts = [
            f"{notice.resolved_notice_type}:recommended",
            f"{notice.resolved_notice_type}:selected",
            "dashboard:metrics",
        ]
        revision, correlation_id = _record_change(
            user=user,
            notice=notice,
            action="procurement.command.select_notice.v1",
            before=before,
            after=after,
            contexts=contexts,
        )

    verified_case = ProcurementCase.objects.filter(
        id=case.id,
        notice_id=notice.id,
        stage=ProcurementCase.Stage.SELECTED,
    ).values("id", "stage").first()
    verified = bool(verified_case)
    return {
        "command": "select_notice.v1",
        "changed": True,
        "idempotent": True,
        "notice_id": str(notice.id),
        "case_id": str(case.id),
        "current_stage": verified_case["stage"] if verified_case else None,
        "revision": revision,
        "correlation_id": str(correlation_id),
        "affected_contexts": contexts,
        "verified": verified,
        "verification": "read_after_write" if verified else "failed",
    }


def confirm_pending_select_v1(*, user, conversation_key: str, lease_id: str, pending_action_id: str, notice_id: str) -> dict:
    conversation_key = normalize_conversation_key(conversation_key)
    require_write_lease(
        user=user,
        conversation_key=conversation_key,
        lease_id=lease_id,
        capability="procurement.select_notice.v1",
    )
    try:
        parsed_pending_id = uuid.UUID(str(pending_action_id))
        parsed_notice_id = uuid.UUID(str(notice_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("Exact pending action and notice UUIDs are required.") from exc

    with transaction.atomic():
        pending = ProcurementPendingAction.objects.select_for_update().filter(
            id=parsed_pending_id,
            user=user,
            conversation_key=conversation_key,
            command="select_notice",
            command_version=1,
        ).first()
        if pending is None:
            raise ValidationError({"pending_action_id": "Pending action not found for this conversation."})
        if pending.expires_at <= timezone.now():
            pending.status = ProcurementPendingAction.Status.EXPIRED
            pending.save(update_fields=["status", "updated_at"])
            raise PermissionDenied("Pending confirmation has expired.")
        if pending.status != ProcurementPendingAction.Status.AWAITING_CONFIRMATION:
            raise ValidationError({"pending_action_id": f"Pending action is already {pending.status}."})
        candidate_ids = {str(item.get("notice_id")) for item in pending.candidates if isinstance(item, dict)}
        if str(parsed_notice_id) not in candidate_ids:
            raise ValidationError({"notice_id": "The confirmed notice is not one of the pending candidates."})
        pending.confirmed_notice_id = parsed_notice_id
        pending.status = ProcurementPendingAction.Status.CONFIRMED
        pending.save(update_fields=["confirmed_notice", "status", "updated_at"])

        result = select_notice_v1(
            user=user,
            conversation_key=conversation_key,
            lease_id=lease_id,
            notice_id=str(parsed_notice_id),
        )
        if not result.get("verified"):
            raise ValidationError("Read-after-write verification failed; pending action was not completed.")
        pending.status = ProcurementPendingAction.Status.EXECUTED
        pending.save(update_fields=["status", "updated_at"])
        AuditEvent.objects.create(
            actor=user.username,
            action="procurement.command.select_notice.v1.confirmed",
            target_type="procurement_pending_action",
            target_id=str(pending.id),
            payload={"notice_id": str(parsed_notice_id), "verified": True},
        )
        return {**result, "pending_action_id": str(pending.id), "confirmation_consumed": True}
