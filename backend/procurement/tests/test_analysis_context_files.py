import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from procurement.models_analysis import AnalysisContextAttachment, AnalysisContextSnapshot


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pdp-context-files-"))
class AnalysisContextFileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        media_root = cls.settings(MEDIA_ROOT=tempfile.gettempdir())
        del media_root
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="analysis-file-manager",
            password="test-pass-123",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.draft = AnalysisContextSnapshot.objects.create(
            version=21,
            status=AnalysisContextSnapshot.Status.DRAFT,
            role_text="نقش آزمایشی",
            base_instructions="دستور پایه",
            analysis_prompt="پرامپت مشترک",
            component_versions={"prompt": 21},
        )

    def test_shared_prompt_is_mirrored_to_legacy_fields(self):
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.analysis_prompt, "پرامپت مشترک")
        self.assertEqual(self.draft.tender_prompt, "پرامپت مشترک")
        self.assertEqual(self.draft.inquiry_prompt, "پرامپت مشترک")

    def test_text_file_upload_is_private_metadata_only(self):
        uploaded = SimpleUploadedFile(
            "keywords.txt",
            "طراحی معماری\nنظارت".encode("utf-8"),
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/v1/procurement/analysis-context-files/",
            {
                "context_snapshot": str(self.draft.id),
                "category": AnalysisContextAttachment.Category.KEYWORDS,
                "file": uploaded,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["original_name"], "keywords.txt")
        self.assertNotIn("file", response.data)
        attachment = AnalysisContextAttachment.objects.get()
        self.assertEqual(attachment.uploaded_by, self.manager)
        self.assertEqual(len(attachment.checksum_sha256), 64)

    def test_active_snapshot_rejects_new_attachment(self):
        self.draft.status = AnalysisContextSnapshot.Status.ACTIVE
        self.draft.save()
        uploaded = SimpleUploadedFile("resume.pdf", b"%PDF-preview", content_type="application/pdf")
        response = self.client.post(
            "/api/v1/procurement/analysis-context-files/",
            {
                "context_snapshot": str(self.draft.id),
                "category": AnalysisContextAttachment.Category.RESUME,
                "file": uploaded,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("context_snapshot", response.data)
