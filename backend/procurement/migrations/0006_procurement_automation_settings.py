import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def create_default_settings(apps, schema_editor):
    Settings = apps.get_model("procurement", "ProcurementAutomationSettings")
    Settings.objects.get_or_create(
        key="default",
        defaults={
            "enabled": False,
            "cadence": "daily",
            "interval_minutes": 60,
            "daily_time": None,
            "timezone_name": "Asia/Tehran",
            "analysis_delay_minutes": 60,
            "scheduled_task_enabled": True,
            "manual_command": "PDP",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0005_analysis_context_and_drafts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcurementAutomationSettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.SlugField(default="default", max_length=40, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("cadence", models.CharField(choices=[("hourly", "ساعتی"), ("daily", "روزانه")], default="daily", max_length=12)),
                ("interval_minutes", models.PositiveIntegerField(default=60)),
                ("daily_time", models.TimeField(blank=True, null=True)),
                ("timezone_name", models.CharField(default="Asia/Tehran", max_length=80)),
                ("analysis_delay_minutes", models.PositiveIntegerField(default=60)),
                ("scheduled_task_enabled", models.BooleanField(default=True)),
                ("manual_command", models.CharField(default="PDP", max_length=40)),
                ("next_extraction_at", models.DateTimeField(blank=True, null=True)),
                ("last_extraction_requested_at", models.DateTimeField(blank=True, null=True)),
                ("last_schedule_sync_at", models.DateTimeField(blank=True, null=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procurement_automation_settings_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "تنظیمات خودکارسازی فرصت‌ها و مناقصات",
                "verbose_name_plural": "تنظیمات خودکارسازی فرصت‌ها و مناقصات",
            },
        ),
        migrations.RunPython(create_default_settings, migrations.RunPython.noop),
    ]
