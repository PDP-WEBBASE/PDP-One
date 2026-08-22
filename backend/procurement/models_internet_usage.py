from django.db import models

from .models import TimestampedModel


class InternetUsageEvent(TimestampedModel):
    """Low-volume, content-free accounting for completed network transfers."""

    class Activity(models.TextChoices):
        ANALYSIS = "analysis", "تحلیل با ChatGPT"
        CI_IMAGES = "ci_images", "CI و ساخت Image"
        DEPLOYMENT = "deployment", "Deploy"
        BACKUP = "backup", "Backup"
        WEB_USERS = "web_users", "کاربران وب"
        UNKNOWN = "unknown", "سایر / نامشخص"

    activity = models.CharField(max_length=24, choices=Activity.choices)
    source = models.CharField(max_length=64)
    download_bytes = models.PositiveBigIntegerField(default=0)
    upload_bytes = models.PositiveBigIntegerField(default=0)
    operation_count = models.PositiveIntegerField(default=1)
    occurred_at = models.DateTimeField()
    reference = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["activity", "occurred_at"], name="proc_net_activity_time_idx")]

