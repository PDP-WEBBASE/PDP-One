from django.conf import settings
from django.db import models

from .models import ProcurementConnector, SourceNotice, TimestampedModel


class ExtractionSchedule(TimestampedModel):
    connector = models.OneToOneField(
        ProcurementConnector,
        on_delete=models.CASCADE,
        related_name="extraction_schedule",
    )
    enabled = models.BooleanField(default=True)
    interval_minutes = models.PositiveIntegerField(default=60)
    include_details = models.BooleanField(default=True)
    analyze_after_success = models.BooleanField(default=True)
    page_cap = models.PositiveIntegerField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["connector__source__name", "connector__notice_type"]


class ExtractionRun(TimestampedModel):
    class Trigger(models.TextChoices):
        MANUAL = "manual", "دستی"
        SCHEDULED = "scheduled", "زمان‌بندی‌شده"
        RETRY = "retry", "تلاش مجدد"

    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        RUNNING = "running", "در حال اجرا"
        SUCCEEDED = "succeeded", "موفق"
        SUCCEEDED_WITH_WARNINGS = "succeeded_with_warnings", "موفق با هشدار"
        PARTIAL = "partial", "ناقص"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "متوقف‌شده"

    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.MANUAL)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    connectors = models.ManyToManyField(ProcurementConnector, related_name="extraction_runs")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_extraction_runs_requested",
    )
    date_from_raw = models.CharField(max_length=40, blank=True)
    date_to_raw = models.CharField(max_length=40, blank=True)
    include_details = models.BooleanField(default=True)
    analyze_after_success = models.BooleanField(default=True)
    page_cap = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    pages_processed = models.PositiveIntegerField(default=0)
    records_seen = models.PositiveIntegerField(default=0)
    records_new = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_duplicate = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="proc_ext_status_created_idx"),
            models.Index(fields=["trigger", "created_at"], name="proc_ext_trigger_created_idx"),
        ]


class ExtractionPage(TimestampedModel):
    class ParseStatus(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SUCCEEDED = "succeeded", "موفق"
        WARNING = "warning", "موفق با هشدار"
        FAILED = "failed", "ناموفق"

    run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="pages")
    connector = models.ForeignKey(ProcurementConnector, on_delete=models.PROTECT, related_name="extraction_pages")
    page_number = models.PositiveIntegerField()
    url = models.URLField(max_length=1000)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    response_bytes = models.PositiveIntegerField(default=0)
    parse_status = models.CharField(max_length=16, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    captured_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ["run", "connector", "page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "connector", "page_number"],
                name="proc_ext_run_conn_page_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["connector", "captured_at"], name="proc_ext_page_captured_idx"),
        ]


class ExtractionRunItem(TimestampedModel):
    class Status(models.TextChoices):
        NEW = "new", "جدید"
        UPDATED = "updated", "به‌روزرسانی‌شده"
        DUPLICATE = "duplicate", "تکراری"
        SKIPPED = "skipped", "ردشده"
        FAILED = "failed", "ناموفق"

    run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="items")
    connector = models.ForeignKey(ProcurementConnector, on_delete=models.PROTECT, related_name="extraction_items")
    source_notice = models.ForeignKey(
        SourceNotice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="extraction_items",
    )
    source_record_id = models.CharField(max_length=160)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    position = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    changed_fields = models.JSONField(default=list, blank=True)
    safe_message = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ["run", "connector", "page_number", "position"]
        indexes = [
            models.Index(fields=["run", "status"], name="proc_ext_item_status_idx"),
            models.Index(fields=["connector", "source_record_id"], name="proc_ext_item_record_idx"),
        ]


class ExtractionError(TimestampedModel):
    class Category(models.TextChoices):
        NETWORK = "network", "شبکه"
        HTTP = "http", "پاسخ سایت"
        PARSE = "parse", "پردازش صفحه"
        SECURITY_CHALLENGE = "security_challenge", "کد امنیتی"
        VALIDATION = "validation", "اعتبارسنجی"
        UNEXPECTED = "unexpected", "پیش‌بینی‌نشده"

    run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="errors")
    connector = models.ForeignKey(ProcurementConnector, on_delete=models.PROTECT, related_name="extraction_errors")
    page_number = models.PositiveIntegerField(null=True, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    category = models.CharField(max_length=24, choices=Category.choices)
    safe_message = models.CharField(max_length=1000)
    technical_details = models.JSONField(default=dict, blank=True)
    retryable = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_extraction_errors_resolved",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["connector", "category", "created_at"], name="proc_ext_error_lookup_idx"),
        ]


from .models_direct import (  # noqa: E402,F401
    DirectOpportunity,
    OpportunityContact,
    OpportunityFollowUp,
    OpportunityResult,
)
