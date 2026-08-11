from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.models import ProcurementNotice
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)


class RecommendedNoticeViewTests(APITestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            username="recommended-view-manager",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.manager)
        self.now = timezone.now()
        self.context = AnalysisContextSnapshot.objects.create(
            version=811,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر",
            base_instructions="فقط خروجی معتبر ChatGPT مبنای پیشنهاد است.",
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
            item_count=4,
        )

    def make_notice(self, title, notice_type=ProcurementNotice.NoticeType.TENDER):
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=title,
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
            first_seen_at=self.now,
            last_seen_at=self.now,
        )

    def make_draft(self, notice, suffix, recommended, analyzed_at, review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT):
        return NoticeAnalysisDraft.objects.create(
            notice=notice,
            batch=self.batch,
            context_snapshot=self.context,
            notice_content_hash=(suffix * 64)[:64],
            is_recommended=recommended,
            score=90 if recommended else 20,
            priority=NoticeAnalysisDraft.Priority.HIGH if recommended else NoticeAnalysisDraft.Priority.LOW,
            fit_for_pdp="متناسب" if recommended else "نامتناسب",
            category="آزمون",
            reason="نتیجه آزمون",
            recommended_action="بررسی" if recommended else "عدم پیگیری",
            confidence=90,
            review_status=review_status,
            analyzed_at=analyzed_at,
        )

    def test_latest_analysis_is_source_of_truth_not_stale_notice_flag(self):
        recommended = self.make_notice("پیشنهاد واقعی", ProcurementNotice.NoticeType.INQUIRY)
        self.make_draft(recommended, "a", True, self.now)
        ProcurementNotice.objects.filter(pk=recommended.pk).update(is_recommended=False)

        stale = self.make_notice("فلگ قدیمی")
        self.make_draft(stale, "b", True, self.now - timedelta(hours=2))
        self.make_draft(stale, "c", False, self.now - timedelta(hours=1))
        ProcurementNotice.objects.filter(pk=stale.pk).update(is_recommended=True)

        rejected = self.make_notice("تحلیل ردشده")
        self.make_draft(
            rejected,
            "d",
            True,
            self.now,
            review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED,
        )
        ProcurementNotice.objects.filter(pk=rejected.pk).update(is_recommended=True)

        response = self.client.get("/api/v1/procurement/recommended-notices/?ordering=-last_seen_at")
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", response.data)
        ids = {str(row["id"]) for row in rows}

        self.assertIn(str(recommended.id), ids)
        self.assertNotIn(str(stale.id), ids)
        self.assertNotIn(str(rejected.id), ids)
        returned = next(row for row in rows if str(row["id"]) == str(recommended.id))
        self.assertTrue(returned["is_recommended"])
