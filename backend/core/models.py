import uuid
from django.conf import settings
from django.db import models


def finance_reference_code():
    return f"FIN-{uuid.uuid4().hex[:10].upper()}"

class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Contract(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        WAITING = "waiting", "در انتظار"
        CRITICAL = "critical", "بحرانی"
        CLOSED = "closed", "خاتمه‌یافته"
    code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=300)
    employer = models.CharField(max_length=250)
    field = models.CharField(max_length=120, blank=True)
    value_rials = models.DecimalField(max_digits=24, decimal_places=0, null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="contracts_created")

class AnalysisReport(TimestampedModel):
    class ReviewStatus(models.TextChoices):
        AI_DRAFT = "ai_draft", "پیش‌نویس هوش مصنوعی"
        REVIEWED = "reviewed", "بازبینی‌شده"
        PUBLISHED = "published", "منتشرشده"
    title = models.CharField(max_length=250)
    summary = models.TextField()
    source_record_ids = models.JSONField(default=list)
    model_label = models.CharField(max_length=80, default="ChatGPT")
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.AI_DRAFT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class Receivable(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        OUTSTANDING = "outstanding", "باز"
        DUE_SOON = "due_soon", "سررسید نزدیک"
        OVERDUE = "overdue", "معوق"
        PENDING_APPROVAL = "pending_approval", "در انتظار تأیید"
        PAID = "paid", "وصول شده"
        CANCELLED = "cancelled", "لغوشده"

    reference_code = models.CharField(max_length=40, unique=True, default=finance_reference_code)
    contract_code = models.CharField(max_length=40)
    contract_title = models.CharField(max_length=300)
    employer = models.CharField(max_length=250)
    statement_title = models.CharField(max_length=200)
    amount_rials = models.DecimalField(max_digits=24, decimal_places=0)
    received_rials = models.DecimalField(max_digits=24, decimal_places=0, default=0)
    due_date = models.DateField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="receivables_created")

    class Meta:
        ordering = ["due_date", "-created_at"]
        indexes = [models.Index(fields=["status", "due_date"], name="core_receiv_status_due_idx")]


class PaymentReceipt(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        CONFIRMED = "confirmed", "تأییدشده"
        REJECTED = "rejected", "ردشده"

    receivable = models.ForeignKey(Receivable, on_delete=models.PROTECT, related_name="receipts")
    amount_rials = models.DecimalField(max_digits=24, decimal_places=0)
    received_date = models.DateField()
    tracking_code = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_receipts_created")

    class Meta:
        ordering = ["-received_date", "-created_at"]

class AuditEvent(TimestampedModel):
    actor = models.CharField(max_length=200)
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)

