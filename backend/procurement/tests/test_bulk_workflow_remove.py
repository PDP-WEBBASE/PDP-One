import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent
from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_documents import ProcurementSubmissionDocument


class BulkWorkflowRemoveTests(APITestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.user = get_user_model().objects.create_user(
            username="bulk-workflow-manager",
            password="test-pass",
            is_staff=True,
        )
        self.other_user = get_user_model().objects.create_user(
            username="bulk-workflow-other",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def make_notice(self, title, stage=None):
        now = timezone.now()
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title=title,
            employer_name="کارفرمای آزمون",
            province="تهران",
            published_date=timezone.localdate(),
            retention_protected=bool(stage),
            first_seen_at=now,
            last_seen_at=now,
        )
        case = None
        if stage:
            case = ProcurementCase.objects.create(
                notice=notice,
                stage=stage,
                created_by=self.user,
                protected_from_retention=True,
            )
        return notice, case

    def bulk_remove(self, workflow, notice_ids):
        return self.client.post(
            f"/api/v1/procurement/ui/workflow/remove-bulk/?notice_type=tender&workflow={workflow}",
            {"notice_ids": [str(value) for value in notice_ids], "reason": "bulk test"},
            format="json",
        )

    def feed(self, workflow):
        return self.client.get(
            f"/api/v1/procurement/ui/notices/?notice_type=tender&workflow={workflow}&page=1&page_size=50"
        )

    def test_recent_bulk_remove_is_user_scoped_view_dismissal_only(self):
        notice, _ = self.make_notice("مناقصه سه روز اخیر")
        before = self.feed("recent")
        self.assertEqual(before.status_code, 200)
        self.assertIn(str(notice.id), {str(row["id"]) for row in before.data["results"]})

        response = self.bulk_remove("recent", [notice.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["removed"], 1)
        self.assertFalse(response.data["notice_deleted"])
        self.assertFalse(response.data["business_stage_changed"])
        self.assertTrue(ProcurementNotice.objects.filter(pk=notice.id).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.user.username,
                action="procurement.workflow.dismiss_from_view",
                target_id=str(notice.id),
                payload__workflow="recent",
            ).exists()
        )

        after = self.feed("recent")
        self.assertEqual(after.status_code, 200)
        self.assertNotIn(str(notice.id), {str(row["id"]) for row in after.data["results"]})

        self.client.force_authenticate(self.other_user)
        other = self.feed("recent")
        self.assertEqual(other.status_code, 200)
        self.assertIn(str(notice.id), {str(row["id"]) for row in other.data["results"]})

    def test_submitted_and_results_remove_only_from_requested_view(self):
        submitted, submitted_case = self.make_notice("مناقصه ارسال شده", ProcurementCase.Stage.SUBMITTED)
        result, result_case = self.make_notice("مناقصه نتیجه شده", ProcurementCase.Stage.WON)

        submitted_response = self.bulk_remove("submitted", [submitted.id])
        self.assertEqual(submitted_response.status_code, 200)
        self.assertEqual(submitted_response.data["removed"], 1)
        submitted_case.refresh_from_db()
        self.assertEqual(submitted_case.stage, ProcurementCase.Stage.SUBMITTED)
        self.assertTrue(ProcurementNotice.objects.filter(pk=submitted.id).exists())
        self.assertNotIn(str(submitted.id), {str(row["id"]) for row in self.feed("submitted").data["results"]})

        result_response = self.bulk_remove("results", [result.id])
        self.assertEqual(result_response.status_code, 200)
        self.assertEqual(result_response.data["removed"], 1)
        result_case.refresh_from_db()
        self.assertEqual(result_case.stage, ProcurementCase.Stage.WON)
        self.assertTrue(ProcurementNotice.objects.filter(pk=result.id).exists())
        self.assertNotIn(str(result.id), {str(row["id"]) for row in self.feed("results").data["results"]})

    def test_selected_bulk_remove_matches_guarded_single_case_semantics(self):
        removable_notice, removable_case = self.make_notice("مناقصه منتخب قابل حذف", ProcurementCase.Stage.SELECTED)
        protected_notice, protected_case = self.make_notice("مناقصه منتخب دارای سند", ProcurementCase.Stage.PREPARING)
        ProcurementSubmissionDocument.objects.create(
            case=protected_case,
            document_type=ProcurementSubmissionDocument.DocumentType.TECHNICAL,
            file=SimpleUploadedFile("proposal.pdf", b"test-pdf-content", content_type="application/pdf"),
            uploaded_by=self.user,
        )

        response = self.bulk_remove("selected", [removable_notice.id, protected_notice.id])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["removed"], 1)
        self.assertEqual(response.data["blocked"], 1)
        self.assertFalse(response.data["notice_deleted"])
        self.assertFalse(ProcurementCase.objects.filter(pk=removable_case.id).exists())
        self.assertTrue(ProcurementCase.objects.filter(pk=protected_case.id).exists())
        self.assertTrue(ProcurementNotice.objects.filter(pk=removable_notice.id).exists())
        removable_notice.refresh_from_db()
        self.assertFalse(removable_notice.retention_protected)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.user.username,
                action="procurement.case.remove_from_selected_bulk",
                payload__notice_id=str(removable_notice.id),
            ).exists()
        )

    def test_bulk_remove_is_bounded_to_current_page_size(self):
        response = self.bulk_remove("recent", [f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 102)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("100", str(response.data))
