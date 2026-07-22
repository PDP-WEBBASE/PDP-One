import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import procurement.models_analysis


def copy_shared_prompt(apps, schema_editor):
    Snapshot = apps.get_model("procurement", "AnalysisContextSnapshot")
    for snapshot in Snapshot.objects.all().iterator():
        snapshot.analysis_prompt = snapshot.tender_prompt or snapshot.inquiry_prompt or ""
        snapshot.save(update_fields=["analysis_prompt"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("procurement", "0007_alter_directopportunity_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysiscontextsnapshot",
            name="analysis_prompt",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(copy_shared_prompt, migrations.RunPython.noop),
        migrations.CreateModel(
            name="AnalysisContextAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(choices=[("prompt_reference", "مرجع نقش و Prompt"), ("keywords", "کلیدواژه‌ها"), ("company_profile", "پروفایل شرکت"), ("qualifications", "صلاحیت‌ها"), ("resume", "رزومه و سوابق"), ("other", "سایر")], max_length=32)),
                ("file", models.FileField(upload_to=procurement.models_analysis.analysis_context_upload_path)),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("checksum_sha256", models.CharField(max_length=64)),
                ("context_snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="procurement.analysiscontextsnapshot")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procurement_analysis_context_files", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["category", "original_name"]},
        ),
        migrations.AddIndex(
            model_name="analysiscontextattachment",
            index=models.Index(fields=["context_snapshot", "category"], name="proc_ctx_file_cat_idx"),
        ),
    ]
