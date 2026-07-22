import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import procurement.models_documents


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0008_analysis_context_prompt_and_attachments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcurementSubmissionDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document_type",
                    models.CharField(
                        choices=[
                            ("technical", "پیشنهاد فنی"),
                            ("financial", "پیشنهاد مالی"),
                            ("resume", "رزومه و سوابق"),
                            ("guarantee", "تضمین و ضمانت‌نامه"),
                            ("letter", "نامه و مکاتبه"),
                            ("receipt", "رسید ارسال"),
                            ("employer_file", "سند کارفرما"),
                            ("other", "سایر"),
                        ],
                        default="other",
                        max_length=24,
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        max_length=500,
                        upload_to=procurement.models_documents.submission_document_path,
                        validators=[procurement.models_documents.validate_submission_file],
                    ),
                ),
                ("original_name", models.CharField(max_length=255)),
                ("description", models.CharField(blank=True, max_length=500)),
                (
                    "case",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submission_documents",
                        to="procurement.procurementcase",
                    ),
                ),
                (
                    "direct_opportunity",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submission_documents",
                        to="procurement.directopportunity",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="procurement_submission_documents_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(
            model_name="procurementsubmissiondocument",
            index=models.Index(fields=["case", "created_at"], name="proc_doc_case_time_idx"),
        ),
        migrations.AddIndex(
            model_name="procurementsubmissiondocument",
            index=models.Index(fields=["direct_opportunity", "created_at"], name="proc_doc_direct_time_idx"),
        ),
    ]
