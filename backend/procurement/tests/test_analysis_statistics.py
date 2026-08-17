from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from procurement.analysis_run_service import create_or_resume_run, initialize_run
from procurement.analysis_statistics import procurement_analysis_statistics
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class ProcurementAnalysisStatisticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analysis-statistics-manager",
            password="test-pass",
            is_staff=True,
        )
        AnalysisContextSnapshot.objects.create(
            version=92,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مناقصات",
            base_instructions="همه نتایج فقط AI Draft هستند.",
            analysis_prompt="فراخوان‌ها را بر اساس تناسب با PDP تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 92},
        )

    def _notice(self, notice_type: str, title: str, offset_minutes: int):
        seen_at = timezone.now() - timedelta(minutes=offset_minutes)
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=title,
            description="خدمات مشاوره و طراحی",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            published_date=seen_at.date(),
        )

    def test_statistics_split_tender_inquiry_and_total(self):
        tender = self._notice(ProcurementNotice.NoticeType.TENDER, "مناقصه آزمون", 2)
        inquiry = self._notice(ProcurementNotice.NoticeType.INQUIRY, "استعلام آزمون", 1)
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        run = initialize_run(str(run.id), actor=self.user.username)

        run.items.filter(notice=tender).update(
            status=ProcurementAnalysisRunItem.Status.COMPLETED,
            attempts=1,
            completed_at=timezone.now(),
        )
        run.items.filter(notice=inquiry).update(
            status=ProcurementAnalysisRunItem.Status.RETRY,
            attempts=2,
            last_error="claim_lease_expired",
        )

        stats = procurement_analysis_statistics(run)

        self.assertEqual(stats["all_notices"], {"tender": 1, "inquiry": 1, "total": 2})
        self.assertEqual(stats["active_run"]["in_run"], {"tender": 1, "inquiry": 1, "total": 2})
        self.assertEqual(stats["active_run"]["attempted_by_chatgpt"]["total"], 2)
        self.assertEqual(stats["active_run"]["completed"], {"tender": 1, "inquiry": 0, "total": 1})
        self.assertEqual(stats["active_run"]["retry"], {"tender": 0, "inquiry": 1, "total": 1})
        self.assertEqual(stats["active_run"]["retry_diagnostics"]["claim_lease_expired"], 1)
        self.assertEqual(stats["claim_policy"]["safe_claim_limit"], 50)
        self.assertTrue(stats["claim_policy"]["one_active_package_per_worker"])

        self.client.force_login(self.user)
        response = self.client.get(reverse("analysis-run-current"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("statistics", response.json())
        self.assertEqual(
            response.json()["statistics"]["active_run"]["in_run"],
            {"tender": 1, "inquiry": 1, "total": 2},
        )
