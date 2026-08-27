from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from procurement.analysis_run_adaptive import (
    SAFE_CLAIM_LIMIT,
    SEMANTIC_SLICE_SIZE,
    admit_newest_pending_items,
    claim_newest_run_items,
)
from procurement.analysis_run_service import create_or_resume_run, initialize_run
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class AdaptiveAnalysisPriorityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="adaptive-analysis-manager",
            password="test-pass",
            is_staff=True,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=91,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مناقصات",
            base_instructions="همه نتایج فقط AI Draft هستند.",
            analysis_prompt="فراخوان‌ها را بر اساس تناسب با PDP تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 91},
        )

    def _notice(self, title: str, seen_at):
        return ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title=title,
            description="خدمات مشاوره و طراحی",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            published_date=seen_at.date(),
        )

    def _run(self):
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        return initialize_run(str(run.id), actor=self.user.username)

    def test_claim_prefers_newest_notice_even_when_sequence_is_older_first(self):
        now = timezone.now()
        old_notice = self._notice("فراخوان قدیمی", now - timedelta(days=5))
        fresh_notice = self._notice("فراخوان جدید", now - timedelta(hours=1))
        run = self._run()

        claimed = claim_newest_run_items(str(run.id), worker_id="priority-worker", limit=1)

        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].notice_id, fresh_notice.id)
        self.assertNotEqual(claimed[0].notice_id, old_notice.id)

    def test_notice_arriving_after_run_start_is_admitted_and_claimed_first(self):
        now = timezone.now()
        self._notice("فراخوان اولیه", now - timedelta(days=2))
        run = self._run()

        fresh_notice = self._notice("فراخوان تازه پس از شروع Run", timezone.now() + timedelta(seconds=1))
        admission = admit_newest_pending_items(str(run.id), actor=self.user.username)
        run.refresh_from_db()

        self.assertEqual(admission["admitted"], 1)
        self.assertTrue(run.items.filter(notice=fresh_notice).exists())
        self.assertEqual(run.metadata["priority_policy"], "newest_first")

        claimed = claim_newest_run_items(str(run.id), worker_id="fresh-worker", limit=1)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].notice_id, fresh_notice.id)

    def test_same_worker_reuses_existing_reservation_until_import_advances_it(self):
        now = timezone.now()
        self._notice("فراخوان اول", now - timedelta(minutes=2))
        self._notice("فراخوان دوم", now - timedelta(minutes=1))
        run = self._run()

        first = claim_newest_run_items(str(run.id), worker_id="same-worker", limit=2)
        second = claim_newest_run_items(str(run.id), worker_id="same-worker", limit=2)

        self.assertEqual([item.id for item in second], [item.id for item in first])
        self.assertEqual(
            run.items.filter(status=ProcurementAnalysisRunItem.Status.CLAIMED, claimed_by="same-worker").count(),
            2,
        )

    def test_global_active_claim_cap_applies_across_workers(self):
        now = timezone.now()
        self._notice("فراخوان اول", now - timedelta(minutes=2))
        self._notice("فراخوان دوم", now - timedelta(minutes=1))
        run = self._run()

        with patch("procurement.analysis_run_adaptive.GLOBAL_ACTIVE_CLAIM_CAP", 1):
            first = claim_newest_run_items(str(run.id), worker_id="worker-a", limit=1)
            second = claim_newest_run_items(str(run.id), worker_id="worker-b", limit=1)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_large_claim_reserves_500_but_returns_only_50_for_semantic_analysis(self):
        now = timezone.now()
        for index in range(SAFE_CLAIM_LIMIT + 10):
            self._notice(f"فراخوان {index}", now + timedelta(seconds=index))
        run = self._run()

        claimed = claim_newest_run_items(str(run.id), worker_id="bounded-worker", limit=500)

        self.assertEqual(SAFE_CLAIM_LIMIT, 500)
        self.assertEqual(SEMANTIC_SLICE_SIZE, 50)
        self.assertEqual(len(claimed), SEMANTIC_SLICE_SIZE)
        self.assertEqual(
            run.items.filter(
                status=ProcurementAnalysisRunItem.Status.CLAIMED,
                claimed_by="bounded-worker",
            ).count(),
            SAFE_CLAIM_LIMIT,
        )

    def test_next_slice_is_returned_after_first_slice_is_checkpointed(self):
        now = timezone.now()
        for index in range(120):
            self._notice(f"فراخوان {index}", now + timedelta(seconds=index))
        run = self._run()

        first = claim_newest_run_items(str(run.id), worker_id="slice-worker", limit=100)
        first_ids = [item.id for item in first]
        run.items.filter(id__in=first_ids).update(status=ProcurementAnalysisRunItem.Status.COMPLETED)

        second = claim_newest_run_items(str(run.id), worker_id="slice-worker", limit=100)

        self.assertEqual(len(first), 50)
        self.assertEqual(len(second), 50)
        self.assertTrue(set(first_ids).isdisjoint({item.id for item in second}))
        self.assertEqual(
            run.items.filter(
                status=ProcurementAnalysisRunItem.Status.CLAIMED,
                claimed_by="slice-worker",
            ).count(),
            50,
        )
