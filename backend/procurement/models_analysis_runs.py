from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .models import ProcurementNotice, TimestampedModel
from .models_analysis import AnalysisContextSnapshot, AnalysisRequest, NoticeAnalysisDraft
from .models_extraction import ExtractionRun


class ProcurementAnalysisRun(TimestampedModel):
    class RunType(models.TextChoices):
        FULL_PENDING = "full_pending_analysis", "تحلیل کامل موارد باقی‌مانده"
        INCREMENTAL = "incremental_analysis", "تحلیل افزایشی"

    class Trigger(models.TextChoices):
        SCHEDULED = "scheduled", "زمان‌بندی‌شده"
        MANUAL_WEB = "manual_web", "دستی از سامانه"
        MANUAL_CHATGPT = "manual_chatgpt", "دستی از ChatGPT"

    class Scope(models.TextChoices):
        ALL_PENDING = "all_pending", "همه موارد باقی‌مانده"
        NEW = "new", "جدید"
        CHANGED = "changed", "تغییریافته"
        RETRY_FAILED = "retry_failed", "تلاش مجدد خطادار"
        MANUAL_SELECTION = "manual_selection", "انتخاب دستی"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PREPARING = "preparing", "در حال آماده‌سازی"
        RUNNING = "running", "در حال پردازش"
        WAITING_FOR_RESULTS = "waiting_for_results", "در انتظار نتایج تحلیل"
        PAUSED = "paused", "متوقف موقت"
        CANCELLING = "cancelling", "در حال لغو"
        CANCELLED = "cancelled", "لغوشده"
        COMPLETED = "completed", "تکمیل‌شده"
        NO_CHANGES = "no_changes", "بدون تغییر"
        FAILED = "failed", "ناموفق"

    ACTIVE_STATUSES = (
        Status.PENDING,
        Status.PREPARING,
        Status.RUNNING,
        Status.WAITING_FOR_RESULTS,
        Status.PAUSED,
        Status.CANCELLING,
    )

    run_type = models.CharField(max_length=32, choices=RunType.choices)
    trigger = models.CharField(max_length=24, choices=Trigger.choices)
    scope = models.CharField(max_length=24, choices=Scope.choices, default=Scope.ALL_PENDING)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    active_key = models.CharField(max_length=40, default="procurement-analysis", editable=False)
    context_snapshot = models.ForeignKey(
        AnalysisContextSnapshot,
        on_delete=models.PROTECT,
        related_name="persistent_analysis_runs",
    )
    extraction_run = models.ForeignKey(
        ExtractionRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="persistent_analysis_runs",
    )
    analysis_request = models.OneToOneField(
        AnalysisRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persistent_run",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_analysis_runs_requested",
    )
    include_expired = models.BooleanField(default=False)
    include_previously_analyzed = models.BooleanField(default=False)
    manual_notice_ids = models.JSONField(default=list, blank=True)
    export_shard_size = models.PositiveIntegerField(default=250)
    deep_analysis_batch_size = models.PositiveIntegerField(default=25)
    parallel_workers = models.PositiveSmallIntegerField(default=4)
    max_retries_per_record = models.PositiveSmallIntegerField(default=2)
    checkpoint_after_each_shard = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_checkpoint = models.JSONField(default=dict, blank=True)
    counters = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["active_key"],
                condition=Q(status__in=[
                    "pending",
                    "preparing",
                    "running",
                    "waiting_for_results",
                    "paused",
                    "cancelling",
                ]),
                name="proc_analysis_single_active_run",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="proc_run_status_created_idx"),
            models.Index(fields=["run_type", "trigger"], name="proc_run_type_trigger_idx"),
        ]


class ProcurementAnalysisRunItem(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        CLAIMED = "claimed", "دریافت‌شده توسط Worker"
        SCREENED = "screened", "غربال‌شده"
        WAITING_DEEP_ANALYSIS = "waiting_deep_analysis", "در انتظار تحلیل عمیق"
        COMPLETED = "completed", "تکمیل‌شده"
        RETRY = "retry", "نیازمند تلاش مجدد"
        POISON = "poison", "رکورد مسئله‌دار"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"
        SKIPPED = "skipped", "نادیده‌گرفته‌شده"

    run = models.ForeignKey(ProcurementAnalysisRun, on_delete=models.CASCADE, related_name="items")
    notice = models.ForeignKey(ProcurementNotice, on_delete=models.PROTECT, related_name="persistent_analysis_items")
    notice_content_hash = models.CharField(max_length=64)
    context_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=28, choices=Status.choices, default=Status.PENDING)
    analysis_reason = models.CharField(max_length=120, blank=True)
    deadline_priority = models.CharField(max_length=16, blank=True)
    shard_number = models.PositiveIntegerField(default=1)
    sequence = models.PositiveIntegerField(default=1)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    claimed_by = models.CharField(max_length=120, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_expires_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    screening = models.JSONField(default=dict, blank=True)
    result_metadata = models.JSONField(default=dict, blank=True)
    draft = models.ForeignKey(
        NoticeAnalysisDraft,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="persistent_run_items",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["run", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["run", "notice"], name="proc_run_notice_uniq"),
            models.UniqueConstraint(
                fields=["run", "claim_token"],
                condition=Q(claim_token__isnull=False),
                name="proc_run_claim_token_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["run", "status", "sequence"], name="proc_item_run_status_idx"),
            models.Index(fields=["claim_expires_at"], name="proc_item_claim_exp_idx"),
        ]

    def new_claim_token(self) -> uuid.UUID:
        self.claim_token = uuid.uuid4()
        return self.claim_token


class ProcurementAnalysisDataset(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PREPARING = "preparing", "در حال تولید"
        READY = "ready", "آماده"
        FAILED = "failed", "ناموفق"

    run = models.ForeignKey(ProcurementAnalysisRun, on_delete=models.CASCADE, related_name="datasets")
    context_snapshot = models.ForeignKey(AnalysisContextSnapshot, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    scope = models.CharField(max_length=24, choices=ProcurementAnalysisRun.Scope.choices)
    schema_version = models.CharField(max_length=40, default="pdp-one.procurement-analysis.v1")
    application_commit = models.CharField(max_length=64, blank=True)
    migration_head = models.CharField(max_length=120, blank=True)
    compression = models.CharField(max_length=16, default="gzip")
    shard_size = models.PositiveIntegerField(default=250)
    record_count = models.PositiveIntegerField(default=0)
    shard_count = models.PositiveIntegerField(default=0)
    files = models.JSONField(default=list, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    hashes = models.JSONField(default=dict, blank=True)
    checkpoint = models.JSONField(default=dict, blank=True)
    validation = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["run", "status"], name="proc_dataset_run_status_idx")]


class ProcurementAnalysisImport(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        VALIDATING = "validating", "در حال اعتبارسنجی"
        IMPORTING = "importing", "در حال ورود"
        COMPLETED = "completed", "تکمیل‌شده"
        PARTIAL = "partial", "ناقص"
        FAILED = "failed", "ناموفق"

    run = models.ForeignKey(ProcurementAnalysisRun, on_delete=models.CASCADE, related_name="imports")
    dataset = models.ForeignKey(ProcurementAnalysisDataset, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    result_hash = models.CharField(max_length=64, blank=True)
    dry_run = models.BooleanField(default=False)
    checkpoint = models.JSONField(default=dict, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    report = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["run", "status"], name="proc_import_run_status_idx")]
