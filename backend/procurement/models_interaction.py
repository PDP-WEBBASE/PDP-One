import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import ProcurementNotice, TimestampedModel


class ProcurementWriteLease(TimestampedModel):
    """Short-lived server-side arming lease for ChatGPT business mutations.

    The opaque conversation_key is supplied by the connected client and is
    bound to the authenticated PDP One user. The lease secret itself is never
    persisted in plaintext; only its SHA-256 digest is stored.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="procurement_write_leases",
    )
    conversation_key = models.CharField(max_length=160)
    token_hash = models.CharField(max_length=64, unique=True)
    scope = models.JSONField(default=list)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "conversation_key", "expires_at"], name="proc_write_lease_scope_idx"),
        ]

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class ProcurementPendingAction(TimestampedModel):
    class Status(models.TextChoices):
        AWAITING_CONFIRMATION = "awaiting_confirmation", "در انتظار تایید"
        CONFIRMED = "confirmed", "تایید شده"
        CANCELLED = "cancelled", "لغو شده"
        EXPIRED = "expired", "منقضی"
        EXECUTED = "executed", "اجرا شده"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="procurement_pending_actions",
    )
    conversation_key = models.CharField(max_length=160)
    command = models.CharField(max_length=120)
    command_version = models.PositiveSmallIntegerField(default=1)
    candidates = models.JSONField(default=list)
    requested_payload = models.JSONField(default=dict)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.AWAITING_CONFIRMATION)
    expires_at = models.DateTimeField()
    confirmed_notice = models.ForeignKey(
        ProcurementNotice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_pending_actions",
    )

    class Meta:
        indexes = [
            models.Index(fields=["user", "conversation_key", "status"], name="proc_pending_action_scope_idx"),
        ]


class ProcurementDomainRevision(models.Model):
    domain = models.CharField(max_length=64, primary_key=True)
    revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ProcurementChangeJournal(TimestampedModel):
    domain = models.CharField(max_length=64, default="procurement")
    revision = models.PositiveBigIntegerField()
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    action = models.CharField(max_length=120)
    affected_contexts = models.JSONField(default=list)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-revision", "-created_at"]
        indexes = [
            models.Index(fields=["domain", "revision"], name="proc_change_domain_rev_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["domain", "revision"], name="proc_change_domain_rev_uniq"),
        ]


class ProcurementOutboxEvent(TimestampedModel):
    event_type = models.CharField(max_length=120)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=100)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    payload = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["published_at", "created_at"], name="proc_outbox_pending_idx"),
        ]
