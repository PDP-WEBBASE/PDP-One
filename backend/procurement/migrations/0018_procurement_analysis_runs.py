import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def configure_hourly_analysis(apps, schema_editor):
    Settings = apps.get_model("procurement", "ProcurementAutomationSettings")
    record = Settings.objects.filter(key="default").first()
    if record is None:
        return
    record.cadence = "hourly"
    record.interval_minutes = 60
    record.analysis_delay_minutes = 0
    record.scheduled_task_enabled = True
    record.save(update_fields=[
        "cadence",
        "interval_minutes",
        "analysis_delay_minutes",
        "scheduled_task_enabled",
        "updated_at",
    ])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("procurement", "0017_seed_analysis_context_v1"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcurementAnalysisRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("run_type", models.CharField(choices=[("full_pending_analysis", "تحلیل کامل موارد باقی‌مانده"), ("incremental_analysis", "تحلیل افزایشی")], max_length=32)),
                ("trigger", models.CharField(choices=[("scheduled", "زمان‌بندی‌شده"), ("manual_web", "دستی از سامانه"), ("manual_chatgpt", "دستی از ChatGPT")], max_length=24)),
                ("scope", models.CharField(choices=[("all_pending", "همه موارد باقی‌مانده"), ("new", "جدید"), ("changed", "تغییریافته"), ("retry_failed", "تلاش مجدد خطادار"), ("manual_selection", "انتخاب دستی")], default="all_pending", max_length=24)),
                ("status", models.CharField(choices=[("pending", "در انتظار"), ("preparing", "در حال آماده‌سازی"), ("running", "در حال پردازش"), ("waiting_for_results", "در انتظار نتایج تحلیل"), ("paused", "متوقف موقت"), ("cancelling", "در حال لغو"), ("cancelled", "لغوشده"), ("completed", "تکمیل‌شده"), ("no_changes", "بدون تغییر"), ("failed", "ناموفق")], default="pending", max_length=32)),
                ("active_key", models.CharField(default="procurement-analysis", editable=False, max_length=40)),
                ("include_expired", models.BooleanField(default=False)),
                ("include_previously_analyzed", models.BooleanField(default=False)),
                ("manual_notice_ids", models.JSONField(blank=True, default=list)),
                ("export_shard_size", models.PositiveIntegerField(default=250)),
                ("deep_analysis_batch_size", models.PositiveIntegerField(default=25)),
                ("parallel_workers", models.PositiveSmallIntegerField(default=4)),
                ("max_retries_per_record", models.PositiveSmallIntegerField(default=2)),
                ("checkpoint_after_each_shard", models.BooleanField(default=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("last_checkpoint", models.JSONField(blank=True, default=dict)),
                ("counters", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_error", models.TextField(blank=True)),
                ("analysis_request", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="persistent_run", to="procurement.analysisrequest")),
                ("context_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="persistent_analysis_runs", to="procurement.analysiscontextsnapshot")),
                ("extraction_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="persistent_analysis_runs", to="procurement.extractionrun")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procurement_analysis_runs_requested", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProcurementAnalysisDataset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "در انتظار"), ("preparing", "در حال تولید"), ("ready", "آماده"), ("failed", "ناموفق")], default="pending", max_length=16)),
                ("scope", models.CharField(choices=[("all_pending", "همه موارد باقی‌مانده"), ("new", "جدید"), ("changed", "تغییریافته"), ("retry_failed", "تلاش مجدد خطادار"), ("manual_selection", "انتخاب دستی")], max_length=24)),
                ("schema_version", models.CharField(default="pdp-one.procurement-analysis.v1", max_length=40)),
                ("application_commit", models.CharField(blank=True, max_length=64)),
                ("migration_head", models.CharField(blank=True, max_length=120)),
                ("compression", models.CharField(default="gzip", max_length=16)),
                ("shard_size", models.PositiveIntegerField(default=250)),
                ("record_count", models.PositiveIntegerField(default=0)),
                ("shard_count", models.PositiveIntegerField(default=0)),
                ("files", models.JSONField(blank=True, default=list)),
                ("counts", models.JSONField(blank=True, default=dict)),
                ("hashes", models.JSONField(blank=True, default=dict)),
                ("checkpoint", models.JSONField(blank=True, default=dict)),
                ("validation", models.JSONField(blank=True, default=dict)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("context_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="procurement.analysiscontextsnapshot")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="datasets", to="procurement.procurementanalysisrun")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProcurementAnalysisImport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "در انتظار"), ("validating", "در حال اعتبارسنجی"), ("importing", "در حال ورود"), ("completed", "تکمیل‌شده"), ("partial", "ناقص"), ("failed", "ناموفق")], default="pending", max_length=16)),
                ("result_hash", models.CharField(blank=True, max_length=64)),
                ("dry_run", models.BooleanField(default=False)),
                ("checkpoint", models.JSONField(blank=True, default=dict)),
                ("counts", models.JSONField(blank=True, default=dict)),
                ("report", models.JSONField(blank=True, default=dict)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("dataset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="procurement.procurementanalysisdataset")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imports", to="procurement.procurementanalysisrun")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProcurementAnalysisRunItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notice_content_hash", models.CharField(max_length=64)),
                ("context_hash", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("pending", "در انتظار"), ("claimed", "دریافت‌شده توسط Worker"), ("screened", "غربال‌شده"), ("waiting_deep_analysis", "در انتظار تحلیل عمیق"), ("completed", "تکمیل‌شده"), ("retry", "نیازمند تلاش مجدد"), ("poison", "رکورد مسئله‌دار"), ("failed", "ناموفق"), ("cancelled", "لغوشده"), ("skipped", "نادیده‌گرفته‌شده")], default="pending", max_length=28)),
                ("analysis_reason", models.CharField(blank=True, max_length=120)),
                ("deadline_priority", models.CharField(blank=True, max_length=16)),
                ("shard_number", models.PositiveIntegerField(default=1)),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("claim_token", models.UUIDField(blank=True, editable=False, null=True)),
                ("claimed_by", models.CharField(blank=True, max_length=120)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("claim_expires_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("screening", models.JSONField(blank=True, default=dict)),
                ("result_metadata", models.JSONField(blank=True, default=dict)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("draft", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="persistent_run_items", to="procurement.noticeanalysisdraft")),
                ("notice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="persistent_analysis_items", to="procurement.procurementnotice")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="procurement.procurementanalysisrun")),
            ],
            options={"ordering": ["run", "sequence"]},
        ),
        migrations.AddConstraint(
            model_name="procurementanalysisrun",
            constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["pending", "preparing", "running", "waiting_for_results", "paused", "cancelling"])), fields=("active_key",), name="proc_analysis_single_active_run"),
        ),
        migrations.AddIndex(model_name="procurementanalysisrun", index=models.Index(fields=["status", "created_at"], name="proc_run_status_created_idx")),
        migrations.AddIndex(model_name="procurementanalysisrun", index=models.Index(fields=["run_type", "trigger"], name="proc_run_type_trigger_idx")),
        migrations.AddIndex(model_name="procurementanalysisdataset", index=models.Index(fields=["run", "status"], name="proc_dataset_run_status_idx")),
        migrations.AddIndex(model_name="procurementanalysisimport", index=models.Index(fields=["run", "status"], name="proc_import_run_status_idx")),
        migrations.AddConstraint(model_name="procurementanalysisrunitem", constraint=models.UniqueConstraint(fields=("run", "notice"), name="proc_run_notice_uniq")),
        migrations.AddConstraint(model_name="procurementanalysisrunitem", constraint=models.UniqueConstraint(condition=models.Q(("claim_token__isnull", False)), fields=("run", "claim_token"), name="proc_run_claim_token_uniq")),
        migrations.AddIndex(model_name="procurementanalysisrunitem", index=models.Index(fields=["run", "status", "sequence"], name="proc_item_run_status_idx")),
        migrations.AddIndex(model_name="procurementanalysisrunitem", index=models.Index(fields=["claim_expires_at"], name="proc_item_claim_exp_idx")),
        migrations.RunPython(configure_hourly_analysis, migrations.RunPython.noop),
    ]
