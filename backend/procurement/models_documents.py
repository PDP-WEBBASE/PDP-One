from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .models import ProcurementCase, TimestampedModel
from .models_direct import DirectOpportunity


ALLOWED_SUBMISSION_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".jpg",
    ".jpeg",
    ".png",
    ".zip",
}
MAX_SUBMISSION_FILE_BYTES = 50 * 1024 * 1024


def validate_submission_file(value):
    suffix = Path(value.name).suffix.lower()
    if suffix not in ALLOWED_SUBMISSION_EXTENSIONS:
        raise ValidationError("نوع فایل برای اسناد پرونده مجاز نیست.")
    if value.size > MAX_SUBMISSION_FILE_BYTES:
        raise ValidationError("حجم هر فایل سند نمی‌تواند بیشتر از ۵۰ مگابایت باشد.")


def submission_document_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    if instance.case_id:
        owner = f"case-{instance.case_id}"
    else:
        owner = f"direct-{instance.direct_opportunity_id}"
    return f"procurement/submission-documents/{owner}/{instance.id}{suffix}"


class ProcurementSubmissionDocument(TimestampedModel):
    class DocumentType(models.TextChoices):
        TECHNICAL = "technical", "پیشنهاد فنی"
        FINANCIAL = "financial", "پیشنهاد مالی"
        RESUME = "resume", "رزومه و سوابق"
        GUARANTEE = "guarantee", "تضمین و ضمانت‌نامه"
        LETTER = "letter", "نامه و مکاتبه"
        RECEIPT = "receipt", "رسید ارسال"
        EMPLOYER_FILE = "employer_file", "سند کارفرما"
        OTHER = "other", "سایر"

    case = models.ForeignKey(
        ProcurementCase,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submission_documents",
    )
    direct_opportunity = models.ForeignKey(
        DirectOpportunity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submission_documents",
    )
    document_type = models.CharField(
        max_length=24,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    file = models.FileField(
        upload_to=submission_document_path,
        validators=[validate_submission_file],
        max_length=500,
    )
    original_name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="procurement_submission_documents_uploaded",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["case", "created_at"], name="proc_doc_case_time_idx"),
            models.Index(fields=["direct_opportunity", "created_at"], name="proc_doc_direct_time_idx"),
        ]

    def clean(self):
        super().clean()
        if bool(self.case_id) == bool(self.direct_opportunity_id):
            raise ValidationError("هر سند باید دقیقاً به یک پرونده مناقصه/استعلام یا یک ارجاع مستقیم متصل باشد.")

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = Path(self.file.name).name[:255]
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        owner = self.case_id or self.direct_opportunity_id
        return f"{self.original_name} — {owner}"
