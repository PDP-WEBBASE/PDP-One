from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent, Contract
from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)


class AIReviewCenterTests(APITestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            username="review-manager",
            password="test-pass",
            is_staff=True,
        )
        self.viewer = get_user_model().objects.create_user(
            username="review-viewer",
            password="test-pass",
        )
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        self.context = AnalysisContextSnapshot.objects.create(
            version=71,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر",
            base_instructions="خروجی فقط پیش‌نویس است.",
            analysis_prompt="تحلیل کن.",
        )
        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_WEB,
            context_snapshot=self.context,
            requested_by=self.manager,
            status=AnalysisRequest.Status.PROCESSING,
        )
        self.batch = AnalysisBatch.objects.create(
            request=request_record,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.PROCESSING,
            sequence=1,
            item_count=2,
        )
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مطالعات و طراحی مرکز آموزشی",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
            is_recommended=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.draft = NoticeAnalysisDraft.objects.create(
            notice=self.notice,
            batch=self.batch,
            context_snapshot=self.context,
            notice_content_hash="a" * 64,
            is_recommended=True,
            score=88,
            priority=NoticeAnalysisDraft.Priority.URGENT,
            fit_for_pdp="متناسب با صلاحیت شرکت",
            category="طراحی آموزشی",
            reason="هم‌راستایی موضوع و صلاحیت",
            recommended_action="بررسی فوری اسناد",
            matched_experience=["طراحی فضای آموزشی"],
            risk_notes=["مهلت کوتاه"],
            confidence=91,
        )

    def test_summary_and_system_status_use_notice_analysis_drafts(self):
        summary = self.client.get("/api/v1/procurement/analysis/review-summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["total"], 1)
        self.assertEqual(summary.data["pending_review"], 1)
        self.assertEqual(summary.data["urgent"], 1)

        system = self.client.get("/api/v1/system-status/")
        self.assertEqual(system.status_code, 200)
        self.assertEqual(system.data["analysis_drafts"], 1)
        self.assertEqual(system.data["analysis_review"]["pending_review"], 1)

    def test_revision_requires_note_and_is_counted_separately(self):
        missing_note = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/review/",
            {"decision": "needs_revision", "note": ""},
            format="json",
        )
        self.assertEqual(missing_note.status_code, 400)

        revised = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/review/",
            {"decision": "needs_revision", "note": "مدارک و شرایط احراز تکمیل شود."},
            format="json",
        )
        self.assertEqual(revised.status_code, 200)
        self.assertTrue(revised.data["needs_revision"])
        self.assertEqual(revised.data["reviewed_by"], self.manager.username)

        summary = self.client.get("/api/v1/procurement/analysis/review-summary/")
        self.assertEqual(summary.data["pending_review"], 0)
        self.assertEqual(summary.data["needs_revision"], 1)

    def test_approve_then_select_creates_one_case_and_no_contract(self):
        contract_count_before = Contract.objects.count()
        approved = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/review/",
            {"decision": "approved", "note": "برای بررسی اسناد تأیید شد."},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["review_status"], NoticeAnalysisDraft.ReviewStatus.REVIEWED)
        self.assertTrue(approved.data["can_select"])

        selected = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/select/",
            {},
            format="json",
        )
        self.assertEqual(selected.status_code, 201)
        self.assertTrue(selected.data["created"])
        self.assertEqual(selected.data["case"]["stage"], ProcurementCase.Stage.SELECTED)

        selected_again = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/select/",
            {},
            format="json",
        )
        self.assertEqual(selected_again.status_code, 200)
        self.assertFalse(selected_again.data["created"])
        self.assertEqual(ProcurementCase.objects.filter(notice=self.notice).count(), 1)
        self.assertEqual(Contract.objects.count(), contract_count_before)
        self.assertTrue(
            AuditEvent.objects.filter(action="procurement.notice_analysis.select_for_followup").exists()
        )

    def test_reject_clears_notice_recommendation(self):
        rejected = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/review/",
            {"decision": "rejected", "note": "موضوع خارج از دامنه خدمات است."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["review_status"], NoticeAnalysisDraft.ReviewStatus.REJECTED)
        self.notice.refresh_from_db()
        self.assertFalse(self.notice.is_recommended)

    def test_non_staff_cannot_review_or_select(self):
        self.client.force_authenticate(self.viewer)
        review = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/review/",
            {"decision": "approved"},
            format="json",
        )
        select = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{self.draft.id}/select/",
            {},
            format="json",
        )
        self.assertEqual(review.status_code, 403)
        self.assertEqual(select.status_code, 403)
