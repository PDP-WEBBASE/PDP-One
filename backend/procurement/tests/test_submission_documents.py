import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditEvent
from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_direct import DirectOpportunity
from procurement.models_documents import ProcurementSubmissionDocument


class ProcurementSubmissionDocumentApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="document-user", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه نمونه",
            employer_name="کارفرمای نمونه",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.case = ProcurementCase.objects.create(
            notice=self.notice,
            stage=ProcurementCase.Stage.SELECTED,
            created_by=self.user,
        )
        self.direct = DirectOpportunity.objects.create(
            title="ارجاع مستقیم نمونه",
            employer_name="کارفرمای مستقیم",
            next_action="",
            stage=DirectOpportunity.Stage.SELECTED,
            created_by=self.user,
        )

    def _pdf(self, name="proposal.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4\npreview", content_type="application/pdf")

    def test_selected_case_document_is_private_and_survives_stage_change(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            response = self.client.post(
                "/api/v1/procurement/submission-documents/",
                {
                    "case": str(self.case.id),
                    "document_type": ProcurementSubmissionDocument.DocumentType.TECHNICAL,
                    "file": self._pdf(),
                    "description": "پیشنهاد فنی",
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 201, response.data)
            document = ProcurementSubmissionDocument.objects.get()
            self.assertEqual(document.original_name, "proposal.pdf")
            self.assertTrue(Path(document.file.path).exists())
            self.assertIn("/download/", response.data["download_url"])
            self.assertNotIn("/data/private", str(response.data))

            self.case.stage = ProcurementCase.Stage.SUBMITTED
            self.case.save(update_fields=["stage", "updated_at"])
            document.refresh_from_db()
            self.assertEqual(document.case_id, self.case.id)
            self.assertTrue(Path(document.file.path).exists())

            download = self.client.get(
                f"/api/v1/procurement/submission-documents/{document.id}/download/"
            )
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download["Cache-Control"], "private, no-store")
            self.assertTrue(
                AuditEvent.objects.filter(
                    action="procurement.submission_document.download",
                    target_id=str(document.id),
                ).exists()
            )

    def test_direct_document_requires_selected_or_later_stage(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            self.direct.stage = DirectOpportunity.Stage.NEW
            self.direct.save(update_fields=["stage", "updated_at"])
            response = self.client.post(
                "/api/v1/procurement/submission-documents/",
                {
                    "direct_opportunity": str(self.direct.id),
                    "document_type": ProcurementSubmissionDocument.DocumentType.RESUME,
                    "file": self._pdf("resume.pdf"),
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("direct_opportunity", response.data)

            self.direct.stage = DirectOpportunity.Stage.SELECTED
            self.direct.save(update_fields=["stage", "updated_at"])
            response = self.client.post(
                "/api/v1/procurement/submission-documents/",
                {
                    "direct_opportunity": str(self.direct.id),
                    "document_type": ProcurementSubmissionDocument.DocumentType.RESUME,
                    "file": self._pdf("resume.pdf"),
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 201, response.data)
            document = ProcurementSubmissionDocument.objects.get()
            self.assertEqual(document.direct_opportunity_id, self.direct.id)

    def test_document_cannot_target_case_and_direct_opportunity_together(self):
        response = self.client.post(
            "/api/v1/procurement/submission-documents/",
            {
                "case": str(self.case.id),
                "direct_opportunity": str(self.direct.id),
                "file": self._pdf(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
