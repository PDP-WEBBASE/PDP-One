import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="AuditEvent", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("actor", models.CharField(max_length=200)), ("action", models.CharField(max_length=120)),
            ("target_type", models.CharField(max_length=100)), ("target_id", models.CharField(blank=True, max_length=100)),
            ("payload", models.JSONField(default=dict)),
        ]),
        migrations.CreateModel(name="Contract", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("code", models.CharField(max_length=40, unique=True)), ("title", models.CharField(max_length=300)),
            ("employer", models.CharField(max_length=250)), ("field", models.CharField(blank=True, max_length=120)),
            ("value_rials", models.DecimalField(blank=True, decimal_places=0, max_digits=24, null=True)),
            ("progress", models.PositiveSmallIntegerField(default=0)), ("due_date", models.DateField(blank=True, null=True)),
            ("status", models.CharField(choices=[("draft", "پیش‌نویس"), ("active", "فعال"), ("waiting", "در انتظار"), ("critical", "بحرانی"), ("closed", "خاتمه‌یافته")], default="draft", max_length=20)),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contracts_created", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="AnalysisReport", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("title", models.CharField(max_length=250)), ("summary", models.TextField()),
            ("source_record_ids", models.JSONField(default=list)), ("model_label", models.CharField(default="ChatGPT", max_length=80)),
            ("review_status", models.CharField(choices=[("ai_draft", "پیش‌نویس هوش مصنوعی"), ("reviewed", "بازبینی‌شده"), ("published", "منتشرشده")], default="ai_draft", max_length=20)),
            ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ]),
    ]

