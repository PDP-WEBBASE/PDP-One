from django.conf import settings
from django.db import models

from .models import TimestampedModel


class ProcurementAutomationSettings(TimestampedModel):
    class Cadence(models.TextChoices):
        HOURLY = "hourly", "ساعتی"
        DAILY = "daily", "روزانه"

    key = models.SlugField(max_length=40, unique=True, default="default")
    enabled = models.BooleanField(default=False)
    cadence = models.CharField(max_length=12, choices=Cadence.choices, default=Cadence.DAILY)
    interval_minutes = models.PositiveIntegerField(default=60)
    daily_time = models.TimeField(null=True, blank=True)
    timezone_name = models.CharField(max_length=80, default="Asia/Tehran")
    analysis_delay_minutes = models.PositiveIntegerField(default=60)
    scheduled_task_enabled = models.BooleanField(default=True)
    manual_command = models.CharField(max_length=40, default="PDP")
    next_extraction_at = models.DateTimeField(null=True, blank=True)
    last_extraction_requested_at = models.DateTimeField(null=True, blank=True)
    last_schedule_sync_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procurement_automation_settings_updated",
    )

    class Meta:
        verbose_name = "تنظیمات خودکارسازی فرصت‌ها و مناقصات"
        verbose_name_plural = "تنظیمات خودکارسازی فرصت‌ها و مناقصات"

    def __str__(self):
        return "تنظیمات خودکارسازی PDP One"
