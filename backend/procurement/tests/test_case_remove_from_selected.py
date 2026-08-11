import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_documents import ProcurementSubmissionDocument


class RemoveSelectedCaseTests(APITestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.user = get_user_model().objects.create_user(
            username="selected-case-manager",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def make_case(self, stage=ProcurementCase.Stage.SELECTED):
        now = timezone.now()
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه آزمون منتخب",
            employer_name="کارفرمای آزمون",
            retention_protected=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        case = ProcurementCase.objects.create(
            notice=notice,
            stage=stage,
            created_by=self.user,
            protected_from_retention=True,
        )
        return notice, case

    def test_delete_removes_only_pre_submission_case_and_keeps_notice(self):
        notice, case = self.make_case()

        response = self.client.delete(f"/api/v1/procurement/cases/{case.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProcurementCase.objects.filter(pk=case.id).exists())
        notice.refresh_from_db()
        self.assertFalse(notice.retention_protected)
        self.assertTrue(ProcurementNotice.objects.filter(pk=notice.id).exists())

    def test_delete_is_blocked_after_submission(self):
        _, case = self.make_case(ProcurementCase.Stage.SUBMITTED)

        response = self.client.delete(f"/api/v1/procurement/cases/{case.id}/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(ProcurementCase.objects.filter(pk=case.id).exists())
        self.assertIn("ارسال", str(response.data))

    def test_delete_is_blocked_when_documents_are_stored(self):
        _, case = self.make_case()
        ProcurementSubmissionDocument.objects.create(
            case=case,
            document_type=ProcurementSubmissionDocument.DocumentType.TECHNICAL,
            file=SimpleUploadedFile("proposal.pdf", b"test-pdf-content", content_type="application/pdf"),
            uploaded_by=self.user,
        )

        response = self.client.delete(f"/api/v1/procurement/cases/{case.id}/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(ProcurementCase.objects.filter(pk=case.id).exists())
        self.assertIn("سند", str(response.data))
