import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0004_directopportunity_opportunitycontact_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalysisContextSnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(unique=True)),
                ("status", models.CharField(choices=[("draft", "پیش‌نویس"), ("active", "فعال"), ("retired", "بازنشسته")], default="draft", max_length=16)),
                ("role_text", models.TextField()),
                ("base_instructions", models.TextField()),
                ("tender_prompt", models.TextField(blank=True)),
                ("inquiry_prompt", models.TextField(blank=True)),
                ("company_profile", models.JSONField(blank=True, default=dict)),
                ("qualifications", models.JSONField(blank=True, default=list)),
                ("keywords", models.JSONField(blank=True, default=dict)),
                ("experience_summary", models.JSONField(blank=True, default=list)),
                ("component_versions", models.JSONField(blank=True, default=dict)),
                ("changed_components", models.JSONField(blank=True, default=list)),
                ("content_hash", models.CharField(blank=True, max_length=64, unique=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("activated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procurement_analysis_contexts_activated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-version"],
                "indexes": [models.Index(fields=["status", "version"], name="proc_ctx_status_ver_idx")],
            },
        ),
        migrations.CreateModel(
            name="AnalysisRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("trigger", models.CharField(choices=[("scheduled", "زمان‌بندی‌شده"), ("manual_chatgpt", "دستی از ChatGPT"), ("manual_web", "دستی از سامانه")], max_length=20)),
                ("command", models.CharField(default="PDP", max_length=40)),
                ("status", models.CharField(choices=[("pending", "در انتظار"), ("processing", "در حال پردازش"), ("completed", "تکمیل‌شده"), ("no_changes", "بدون داده جدید"), ("failed", "ناموفق")], default="pending", max_length=20)),
                ("eligible_after", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=1000)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("context_snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="analysis_requests", to="procurement.analysiscontextsnapshot")),
                ("extraction_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="analysis_requests", to="procurement.extractionrun")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procurement_analysis_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status", "eligible_after"], name="proc_req_status_due_idx"),
                    models.Index(fields=["trigger", "created_at"], name="proc_req_trigger_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AnalysisBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("open", "باز"), ("processing", "در حال پردازش"), ("completed", "تکمیل‌شده"), ("partial", "ناقص"), ("failed", "ناموفق")], default="open", max_length=16)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("item_count", models.PositiveIntegerField(default=0)),
                ("completed_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("context_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="analysis_batches", to="procurement.analysiscontextsnapshot")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="procurement.analysisrequest")),
            ],
            options={"ordering": ["request", "sequence"]},
        ),
        migrations.CreateModel(
            name="NoticeAnalysisDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notice_content_hash", models.CharField(max_length=64)),
                ("is_recommended", models.BooleanField(default=False)),
                ("score", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("priority", models.CharField(choices=[("low", "پایین"), ("medium", "متوسط"), ("high", "بالا"), ("urgent", "فوری")], default="medium", max_length=12)),
                ("fit_for_pdp", models.TextField()),
                ("category", models.CharField(blank=True, max_length=200)),
                ("reason", models.TextField()),
                ("recommended_action", models.TextField()),
                ("matched_experience", models.JSONField(blank=True, default=list)),
                ("risk_notes", models.JSONField(blank=True, default=list)),
                ("confidence", models.DecimalField(decimal_places=2, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("raw_output", models.JSONField(blank=True, default=dict)),
                ("model_label", models.CharField(default="ChatGPT Scheduled Task", max_length=100)),
                ("review_status", models.CharField(choices=[("ai_draft", "پیش‌نویس ChatGPT"), ("reviewed", "بازبینی‌شده"), ("published", "منتشرشده"), ("rejected", "ردشده")], default="ai_draft", max_length=16)),
                ("analyzed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_by_label", models.CharField(default="ChatGPT", max_length=120)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="drafts", to="procurement.analysisbatch")),
                ("context_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notice_analysis_drafts", to="procurement.analysiscontextsnapshot")),
                ("notice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="analysis_drafts", to="procurement.procurementnotice")),
            ],
            options={
                "ordering": ["-analyzed_at"],
                "indexes": [
                    models.Index(fields=["is_recommended", "priority"], name="proc_ana_rec_prio_idx"),
                    models.Index(fields=["review_status", "analyzed_at"], name="proc_ana_review_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="analysisbatch",
            constraint=models.UniqueConstraint(fields=("request", "sequence"), name="proc_batch_request_seq_uniq"),
        ),
        migrations.AddConstraint(
            model_name="noticeanalysisdraft",
            constraint=models.UniqueConstraint(fields=("notice", "notice_content_hash", "context_snapshot"), name="proc_ana_notice_basis_uniq"),
        ),
    ]
