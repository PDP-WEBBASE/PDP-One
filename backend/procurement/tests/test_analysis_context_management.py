import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from procurement.models_analysis import AnalysisContextAttachment, AnalysisContextSnapshot


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pdp-analysis-management-"))
class AnalysisContextManagementTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="analysis-manager",
            password="test-pass",
            is_staff=True,
        )
        self.viewer = User.objects.create_user(username="analysis-viewer", password="test-pass")
        self.client.force_authenticate(self.manager)
        self.active = AnalysisContextSnapshot.objects.create(
            version=1,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="نقش فعال",
            base_instructions="دستور پایه فعال",
            analysis_prompt="پرامپت مشترک فعال",
            company_profile={"name": "PDP", "summary": "پروفایل"},
            qualifications=["معماری"],
            keywords={"active": ["مطالعات"], "excluded": []},
            experience_summary=[{"title": "مطالعات نمونه"}],
            component_versions={
                "snapshot": 1,
                "role": 1,
                "prompt": 1,
                "company_profile": 1,
                "qualifications": 1,
                "keywords": 1,
                "experience_summary": 1,
            },
            changed_components=["initial"],
        )
        self.active_file = AnalysisContextAttachment.objects.create(
            context_snapshot=self.active,
            category=AnalysisContextAttachment.Category.RESUME,
            file=SimpleUploadedFile("resume.pdf", b"%PDF-context", content_type="application/pdf"),
            original_name="resume.pdf",
            content_type="application/pdf",
            size_bytes=12,
            checksum_sha256="a" * 64,
            uploaded_by=self.manager,
        )

    def create_draft(self):
        return self.client.post(
            "/api/v1/procurement/analysis-contexts/create-draft/",
            {"source_snapshot": str(self.active.id)},
            format="json",
        )

    def test_create_draft_clones_active_context_and_attachments(self):
        response = self.create_draft()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(response.data["status"], AnalysisContextSnapshot.Status.DRAFT)
        self.assertFalse(response.data["is_locked"])
        self.assertEqual(response.data["role_text"], self.active.role_text)
        self.assertEqual(len(response.data["attachments"]), 1)
        draft = AnalysisContextSnapshot.objects.get(pk=response.data["id"])
        self.assertEqual(draft.component_versions["snapshot"], 2)
        self.assertNotEqual(draft.content_hash, self.active.content_hash)

        reused = self.create_draft()
        self.assertEqual(reused.status_code, 200)
        self.assertTrue(reused.data["reused_draft"])
        self.assertEqual(AnalysisContextSnapshot.objects.filter(status="draft").count(), 1)

    def test_active_context_is_locked_and_draft_tracks_component_versions(self):
        locked = self.client.patch(
            f"/api/v1/procurement/analysis-contexts/{self.active.id}/",
            {"role_text": "تغییر غیرمجاز"},
            format="json",
        )
        self.assertEqual(locked.status_code, 400)

        draft_response = self.create_draft()
        draft_id = draft_response.data["id"]
        updated = self.client.patch(
            f"/api/v1/procurement/analysis-contexts/{draft_id}/",
            {
                "role_text": "نقش اصلاح‌شده",
                "keywords": {"active": ["مطالعات", "شهرسازی"], "excluded": ["خرید کالا"]},
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertCountEqual(updated.data["changed_components"], ["role", "keywords"])
        self.assertEqual(updated.data["component_versions"]["role"], 2)
        self.assertEqual(updated.data["component_versions"]["keywords"], 2)

    def test_activate_retires_previous_context_and_locks_new_version(self):
        draft_response = self.create_draft()
        draft_id = draft_response.data["id"]
        activated = self.client.post(
            f"/api/v1/procurement/analysis-contexts/{draft_id}/activate/",
            {},
            format="json",
        )
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.data["status"], AnalysisContextSnapshot.Status.ACTIVE)
        self.assertTrue(activated.data["is_locked"])
        self.active.refresh_from_db()
        self.assertEqual(self.active.status, AnalysisContextSnapshot.Status.RETIRED)

    def test_keyword_spreadsheet_upload_and_draft_delete(self):
        draft_response = self.create_draft()
        draft_id = draft_response.data["id"]
        upload = self.client.post(
            "/api/v1/procurement/analysis-context-files/",
            {
                "context_snapshot": draft_id,
                "category": AnalysisContextAttachment.Category.KEYWORDS,
                "file": SimpleUploadedFile(
                    "keywords.xlsx",
                    b"PK-spreadsheet-placeholder",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201)
        self.assertTrue(upload.data["download_url"].endswith("/download/"))

        deleted = self.client.delete(f"/api/v1/procurement/analysis-context-files/{upload.data['id']}/")
        self.assertEqual(deleted.status_code, 204)

    def test_category_extension_and_locked_file_delete_are_enforced(self):
        draft_response = self.create_draft()
        bad = self.client.post(
            "/api/v1/procurement/analysis-context-files/",
            {
                "context_snapshot": draft_response.data["id"],
                "category": AnalysisContextAttachment.Category.RESUME,
                "file": SimpleUploadedFile("resume.csv", b"a,b", content_type="text/csv"),
            },
            format="multipart",
        )
        self.assertEqual(bad.status_code, 400)
        locked_delete = self.client.delete(
            f"/api/v1/procurement/analysis-context-files/{self.active_file.id}/"
        )
        self.assertEqual(locked_delete.status_code, 400)

    def test_non_staff_user_cannot_create_draft(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(
            "/api/v1/procurement/analysis-contexts/create-draft/",
            {"source_snapshot": str(self.active.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
