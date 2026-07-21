import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProcurementSource(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال توسط کاربر"
        PENDING = "pending_source_analysis", "در انتظار بررسی فنی"
        DEGRADED = "degraded", "دارای اختلال"

    key = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    base_url = models.URLField(max_length=500)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    configuration = models.JSONField(default=dict, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProcurementConnector(TimestampedModel):
    class NoticeType(models.TextChoices):
        TENDER = "tender", "مناقصه"
        INQUIRY = "inquiry", "استعلام"

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال توسط کاربر"
        PENDING = "pending_source_analysis", "در انتظار بررسی فنی"
        ERROR = "error", "خطا"

    source = models.ForeignKey(ProcurementSource, on_delete=models.PROTECT, related_name="connectors")
    key = models.SlugField(max_length=80, unique=True)
    notice_type = models.CharField(max_length=12, choices=NoticeType.choices)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    list_url_template = models.CharField(max_length=500)
    parser_version = models.CharField(max_length=80, default="v1")
    supports_detail = models.BooleanField(default=True)
    requires_browser = models.BooleanField(default=False)
    page_size_hint = models.PositiveSmallIntegerField(null=True, blank=True)
    max_pages = models.PositiveIntegerField(default=100)
    timeout_seconds = models.PositiveSmallIntegerField(default=60)
    retry_count = models.PositiveSmallIntegerField(default=3)
    overlap_days = models.PositiveSmallIntegerField(default=2)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_successful_page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["source__name", "notice_type"]
        constraints = [
            models.UniqueConstraint(fields=["source", "notice_type"], name="proc_source_notice_type_uniq"),
        ]

    def __str__(self):
        return self.key


class SourceNotice(TimestampedModel):
    class DetailStatus(models.TextChoices):
        NOT_REQUESTED = "not_requested", "درخواست نشده"
        ENRICHED = "enriched", "تکمیل‌شده"
        ACCESS_LIMITED = "access_limited", "دسترسی محدود"
        SECURITY_CHALLENGE = "security_challenge", "کد امنیتی"
        FAILED = "failed", "ناموفق"

    connector = models.ForeignKey(ProcurementConnector, on_delete=models.PROTECT, related_name="source_notices")
    source_record_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000)
    detail_url = models.URLField(max_length=1000, blank=True)
    source_declared_type = models.CharField(max_length=12, choices=ProcurementConnector.NoticeType.choices)
    title_raw = models.CharField(max_length=600)
    employer_raw = models.CharField(max_length=400, blank=True)
    province_raw = models.CharField(max_length=120, blank=True)
    published_at_raw = models.CharField(max_length=120, blank=True)
    deadline_raw = models.CharField(max_length=120, blank=True)
    raw_payload = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    detail_status = models.CharField(max_length=24, choices=DetailStatus.choices, default=DetailStatus.NOT_REQUESTED)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(fields=["connector", "source_record_id"], name="proc_connector_record_uniq"),
        ]
        indexes = [
            models.Index(fields=["connector", "last_seen_at"], name="proc_src_connector_seen_idx"),
            models.Index(fields=["content_hash"], name="proc_src_hash_idx"),
        ]

    def __str__(self):
        return f"{self.connector.key}:{self.source_record_id}"


class SourceNoticeRevision(TimestampedModel):
    source_notice = models.ForeignKey(SourceNotice, on_delete=models.CASCADE, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    raw_payload = models.JSONField(default=dict)
    parsed_payload = models.JSONField(default=dict)
    changed_fields = models.JSONField(default=list)
    parser_version = models.CharField(max_length=80)
    captured_at = models.DateTimeField()

    class Meta:
        ordering = ["source_notice", "revision_number"]
        constraints = [
            models.UniqueConstraint(fields=["source_notice", "revision_number"], name="proc_notice_revision_uniq"),
        ]


class ProcurementNotice(TimestampedModel):
    class NoticeType(models.TextChoices):
        TENDER = "tender", "مناقصه"
        INQUIRY = "inquiry", "استعلام"

    class TypeResolutionStatus(models.TextChoices):
        RESOLVED = "resolved", "تعیین‌شده"
        NEEDS_REVIEW = "needs_review", "نیازمند بررسی نوع"

    class ProcessingStatus(models.TextChoices):
        CAPTURED = "captured", "دریافت‌شده"
        NORMALIZED = "normalized", "استانداردشده"
        READY_FOR_ANALYSIS = "ready_for_analysis", "آماده تحلیل"
        ANALYSIS_QUEUED = "analysis_queued", "در صف تحلیل"
        ANALYZED = "analyzed", "تحلیل‌شده"
        ANALYSIS_FAILED = "analysis_failed", "تحلیل ناموفق"
        EXPIRED = "expired", "مهلت گذشته"
        RETENTION_CLEANED = "retention_cleaned", "پاک‌سازی‌شده"

    resolved_notice_type = models.CharField(max_length=12, choices=NoticeType.choices)
    type_resolution_status = models.CharField(
        max_length=20,
        choices=TypeResolutionStatus.choices,
        default=TypeResolutionStatus.RESOLVED,
    )
    title = models.CharField(max_length=600)
    normalized_title = models.CharField(max_length=600, blank=True)
    summary = models.TextField(blank=True)
    description = models.TextField(blank=True)
    conditions = models.TextField(blank=True)
    employer_name = models.CharField(max_length=400, blank=True)
    notice_number = models.CharField(max_length=160, blank=True)
    province = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    execution_location = models.CharField(max_length=300, blank=True)
    published_date = models.DateField(null=True, blank=True)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    date_metadata = models.JSONField(default=dict, blank=True)
    estimated_amount_rials = models.DecimalField(max_digits=24, decimal_places=0, null=True, blank=True)
    guarantee_amount_rials = models.DecimalField(max_digits=24, decimal_places=0, null=True, blank=True)
    qualification_text = models.TextField(blank=True)
    contact_text = models.TextField(blank=True)
    processing_status = models.CharField(
        max_length=24,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.CAPTURED,
    )
    is_recommended = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    retention_protected = models.BooleanField(default=False)
    soft_deleted_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["resolved_notice_type", "submission_deadline"], name="proc_notice_type_deadline_idx"),
            models.Index(fields=["processing_status", "is_recommended"], name="proc_notice_status_rec_idx"),
            models.Index(fields=["employer_name"], name="proc_notice_employer_idx"),
            models.Index(fields=["province"], name="proc_notice_province_idx"),
        ]

    def __str__(self):
        return self.title


class NoticeSourceLink(TimestampedModel):
    class MatchType(models.TextChoices):
        EXACT = "exact", "قطعی"
        PROBABLE = "probable", "احتمالی"
        POSSIBLE = "possible", "ممکن"
        MANUAL = "manual", "تأیید دستی"

    procurement_notice = models.ForeignKey(ProcurementNotice, on_delete=models.CASCADE, related_name="source_links")
    source_notice = models.OneToOneField(SourceNotice, on_delete=models.PROTECT, related_name="notice_link")
    match_type = models.CharField(max_length=12, choices=MatchType.choices, default=MatchType.EXACT)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    rationale = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_source_links_confirmed",
    )


class ProcurementCase(TimestampedModel):
    class Stage(models.TextChoices):
        SELECTED = "selected", "منتخب"
        EVALUATING = "evaluating", "در حال ارزیابی"
        PARTICIPATE = "participate", "تصمیم به شرکت یا پاسخ"
        DO_NOT_PARTICIPATE = "do_not_participate", "تصمیم به عدم شرکت یا پاسخ"
        PREPARING = "preparing", "در دست تهیه"
        READY_TO_SUBMIT = "ready_to_submit", "آماده ارسال"
        SUBMITTED = "submitted", "ارسال‌شده"
        AWAITING_RESULT = "awaiting_result", "در انتظار نتیجه"
        WON = "won", "برنده"
        LOST = "lost", "بازنده"
        CANCELLED = "cancelled", "لغوشده"
        RENEWED = "renewed", "تجدیدشده"

    notice = models.OneToOneField(ProcurementNotice, on_delete=models.PROTECT, related_name="case")
    stage = models.CharField(max_length=24, choices=Stage.choices, default=Stage.SELECTED)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="procurement_cases_responsible",
    )
    next_action = models.CharField(max_length=500, blank=True)
    next_action_due = models.DateTimeField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    decision_reason = models.CharField(max_length=500, blank=True)
    protected_from_retention = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="procurement_cases_created",
    )

    class Meta:
        ordering = ["next_action_due", "-created_at"]
        indexes = [
            models.Index(fields=["stage", "next_action_due"], name="proc_case_stage_due_idx"),
            models.Index(fields=["responsible", "stage"], name="proc_case_owner_stage_idx"),
        ]

    def __str__(self):
        return f"{self.notice.title} — {self.get_stage_display()}"


from .models_extraction import (  # noqa: E402,F401
    ExtractionError,
    ExtractionPage,
    ExtractionRun,
    ExtractionRunItem,
    ExtractionSchedule,
)
