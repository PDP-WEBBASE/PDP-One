import hashlib
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .models import ProcurementNotice, TimestampedModel
from .models_extraction import ExtractionRun


def analysis_context_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()[:12]
    return f"procurement/analysis-context/{instance.context_snapshot_id}/{uuid.uuid4().hex}{suffix}"


class AnalysisContextSnapshot(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        RETIRED = "retired", "بازنشسته"

    version = models.PositiveIntegerField(unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    role_text = models.TextField()
    base_instructions = models.TextField()
    analysis_prompt = models.TextField(blank=True)
    tender_prompt = models.TextField(blank=True)
    inquiry_prompt = models.TextField(blank=True)
    company_profile = models.JSONField(default=dict, blank=True)
    qualifications = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=dict, blank=True)
    experience_summary = models.JSONField(default=list, blank=True)
    component_versions = models.JSONField(default=dict, blank=True)
    changed_components = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, unique=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_analysis_contexts_activated",
    )

    class Meta:
        ordering = ["-version"]
        indexes = [
            models.Index(fields=["status", "version"], name="proc_ctx_status_ver_idx"),
        ]

    def calculate_content_hash(self) -> str:
        payload = {
            "role_text": self.role_text,
            "base_instructions": self.base_instructions,
            "analysis_prompt": self.analysis_prompt,
            "company_profile": self.company_profile,
            "qualifications": self.qualifications,
            "keywords": self.keywords,
            "experience_summary": self.experience_summary,
            "component_versions": self.component_versions,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def save(self, *args, **kwargs):
        if self.analysis_prompt:
            self.tender_prompt = self.analysis_prompt
            self.inquiry_prompt = self.analysis_prompt
        else:
            self.analysis_prompt = self.tender_prompt or self.inquiry_prompt
            self.tender_prompt = self.analysis_prompt
            self.inquiry_prompt = self.analysis_prompt
        self.content_hash = self.calculate_content_hash()
        if self.status == self.Status.ACTIVE and self.activated_at is None:
            self.activated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Analysis context v{self.version}"


class AnalysisContextAttachment(TimestampedModel):
    class Category(models.TextChoices):
        PROMPT_REFERENCE = "prompt_reference", "مرجع نقش و Prompt"
        KEYWORDS = "keywords", "کلیدواژه‌ها"
        COMPANY_PROFILE = "company_profile", "پروفایل شرکت"
        QUALIFICATIONS = "qualifications", "صلاحیت‌ها"
        RESUME = "resume", "رزومه و سوابق"
        OTHER = "other", "سایر"

    context_snapshot = models.ForeignKey(
        AnalysisContextSnapshot,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    file = models.FileField(upload_to=analysis_context_upload_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_analysis_context_files",
    )

    class Meta:
        ordering = ["category", "original_name"]
        indexes = [
            models.Index(fields=["context_snapshot", "category"], name="proc_ctx_file_cat_idx"),
        ]

    def __str__(self):
        return self.original_name


class AnalysisRequest(TimestampedModel):
    class Trigger(models.TextChoices):
        SCHEDULED = "scheduled", "زمان‌بندی‌شده"
        MANUAL_CHATGPT = "manual_chatgpt", "دستی از ChatGPT"
        MANUAL_WEB = "manual_web", "دستی از سامانه"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSING = "processing", "در حال پردازش"
        COMPLETED = "completed", "تکمیل‌شده"
        NO_CHANGES = "no_changes", "بدون داده جدید"
        FAILED = "failed", "ناموفق"

    trigger = models.CharField(max_length=20, choices=Trigger.choices)
    command = models.CharField(max_length=40, default="PDP")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    extraction_run = models.ForeignKey(
        ExtractionRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="analysis_requests",
    )
    context_snapshot = models.ForeignKey(
        AnalysisContextSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="analysis_requests",
    )
    eligible_after = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_analysis_requests",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "eligible_after"], name="proc_req_status_due_idx"),
            models.Index(fields=["trigger", "created_at"], name="proc_req_trigger_idx"),
        ]


class AnalysisBatch(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "باز"
        PROCESSING = "processing", "در حال پردازش"
        COMPLETED = "completed", "تکمیل‌شده"
        PARTIAL = "partial", "ناقص"
        FAILED = "failed", "ناموفق"

    request = models.ForeignKey(AnalysisRequest, on_delete=models.CASCADE, related_name="batches")
    context_snapshot = models.ForeignKey(
        AnalysisContextSnapshot,
        on_delete=models.PROTECT,
        related_name="analysis_batches",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    sequence = models.PositiveIntegerField(default=1)
    item_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["request", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["request", "sequence"], name="proc_batch_request_seq_uniq"),
        ]


class NoticeAnalysisDraft(TimestampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "پایین"
        MEDIUM = "medium", "متوسط"
        HIGH = "high", "بالا"
        URGENT = "urgent", "فوری"

    class ReviewStatus(models.TextChoices):
        AI_DRAFT = "ai_draft", "پیش‌نویس ChatGPT"
        REVIEWED = "reviewed", "بازبینی‌شده"
        PUBLISHED = "published", "منتشرشده"
        REJECTED = "rejected", "ردشده"

    notice = models.ForeignKey(ProcurementNotice, on_delete=models.PROTECT, related_name="analysis_drafts")
    batch = models.ForeignKey(AnalysisBatch, on_delete=models.PROTECT, related_name="drafts")
    context_snapshot = models.ForeignKey(
        AnalysisContextSnapshot,
        on_delete=models.PROTECT,
        related_name="notice_analysis_drafts",
    )
    notice_content_hash = models.CharField(max_length=64)
    is_recommended = models.BooleanField(default=False)
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    fit_for_pdp = models.TextField()
    category = models.CharField(max_length=200, blank=True)
    reason = models.TextField()
    recommended_action = models.TextField()
    matched_experience = models.JSONField(default=list, blank=True)
    risk_notes = models.JSONField(default=list, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    raw_output = models.JSONField(default=dict, blank=True)
    model_label = models.CharField(max_length=100, default="ChatGPT Scheduled Task")
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.AI_DRAFT,
    )
    analyzed_at = models.DateTimeField(default=timezone.now)
    created_by_label = models.CharField(max_length=120, default="ChatGPT")

    class Meta:
        ordering = ["-analyzed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["notice", "notice_content_hash", "context_snapshot"],
                name="proc_ana_notice_basis_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["is_recommended", "priority"], name="proc_ana_rec_prio_idx"),
            models.Index(fields=["review_status", "analyzed_at"], name="proc_ana_review_idx"),
            models.Index(
                fields=["notice", "-analyzed_at", "-created_at", "-id"],
                name="proc_ana_notice_latest_idx",
            ),
        ]
