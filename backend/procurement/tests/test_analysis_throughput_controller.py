from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from procurement.analysis_run_adaptive import claim_newest_run_items, renew_worker_claim
from procurement.analysis_run_service import create_or_resume_run, initialize_run
from procurement.analysis_throughput import adaptive_throughput_policy
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class AnalysisThroughputControllerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analysis-throughput-manager",
            password="test-pass",
            is_staff=True,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=93,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مناقصات",
            base_instructions="همه نتایج فقط AI Draft هستند.",
            analysis_prompt="فراخوان‌ها را بر اساس تناسب واقعی با PDP تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 93},
        )

    def _notice(self, title: str):
        seen_at = timezone.now() - timedelta(minutes=1)
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

    def _active_reanalysis_run(self):
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
            include_previously_analyzed=True,
        )
        self.assertTrue(created)
        return initialize_run(str(run.id), actor=self.user.username)

    def _draft(self, run, notice, content_hash, *, raw_output=None):
        batch = run.analysis_request.batches.order_by("sequence").first()
        return NoticeAnalysisDraft.objects.create(
            notice=notice,
            batch=batch,
            context_snapshot=run.context_snapshot,
            notice_content_hash=content_hash,
            is_recommended=False,
            score=10,
            priority=NoticeAnalysisDraft.Priority.LOW,
            fit_for_pdp="تناسب پایین",
            category="test",
            reason="تحلیل معتبر قبلی",
            recommended_action="عدم پیگیری",
            matched_experience=[],
            risk_notes=[],
            confidence=90,
            raw_output=raw_output or {},
            model_label="test",
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
            created_by_label="test",
        )

    def test_policy_targets_30k_with_40_logical_lanes_and_40k_design_capacity(self):
        at_40k = adaptive_throughput_policy(41404)
        at_50k = adaptive_throughput_policy(51000)

        for policy in (at_40k, at_50k):
            self.assertEqual(policy["target_per_hour"], 30000)
            self.assertEqual(policy["desired_lanes"], 40)
            self.assertEqual(policy["package_size"], 50)
            self.assertEqual(policy["micro_batch_size"], 50)
            self.assertEqual(policy["claim_reservation_size"], 250)
            self.assertEqual(policy["claim_window_target_per_lane"], 1000)
            self.assertEqual(policy["per_lane_hourly_ceiling"], 1000)
            self.assertEqual(policy["max_packages_per_lane"], 20)
            self.assertEqual(policy["planned_capacity_per_hour"], 40000)

    def test_backpressure_reduces_package_cycles_when_recent_leases_expire(self):
        policy = adaptive_throughput_policy(
            41404,
            recent_completed=100,
            recent_lease_expired=100,
        )

        self.assertEqual(policy["backpressure"], "degraded")
        self.assertEqual(policy["lease_stability_band"], "degraded")
        self.assertEqual(policy["ramp_target_per_hour"], 5000)
        self.assertEqual(policy["max_packages_per_lane"], 3)
        self.assertEqual(policy["planned_capacity_per_hour"], 6000)
        self.assertEqual(policy["package_size"], 50)
        self.assertEqual(policy["claim_reservation_size"], 250)

    def test_stable_lease_ratio_ramps_capacity_by_observed_imports(self):
        first_stage = adaptive_throughput_policy(
            50000,
            recent_completed=2500,
            recent_lease_expired=0,
        )
        second_stage = adaptive_throughput_policy(
            50000,
            recent_completed=6000,
            recent_lease_expired=0,
        )
        full_stage = adaptive_throughput_policy(
            50000,
            recent_completed=31000,
            recent_lease_expired=0,
        )

        self.assertEqual(first_stage["lease_stability_band"], "stable")
        self.assertEqual(first_stage["ramp_target_per_hour"], 5000)
        self.assertEqual(first_stage["planned_capacity_per_hour"], 6000)
        self.assertEqual(second_stage["ramp_target_per_hour"], 10000)
        self.assertEqual(second_stage["planned_capacity_per_hour"], 10000)
        self.assertEqual(full_stage["ramp_target_per_hour"], 40000)
        self.assertEqual(full_stage["planned_capacity_per_hour"], 40000)

    def test_renewal_is_capped_at_90_minutes_and_hard_age_blocks_old_reservation(self):
        self._notice("فراخوان برای lease نود دقیقه")
        run = self._active_reanalysis_run()
        claimed = claim_newest_run_items(
            str(run.id),
            worker_id="lease-v31-worker",
            limit=1,
            lease_seconds=99999,
        )
        self.assertEqual(len(claimed), 1)
        claimed[0].refresh_from_db()
        self.assertLessEqual(
            claimed[0].claim_expires_at,
            timezone.now() + timedelta(seconds=5405),
        )

        run.items.filter(pk=claimed[0].pk).update(
            claimed_at=timezone.now() - timedelta(hours=5),
            claim_expires_at=timezone.now() + timedelta(minutes=30),
        )
        renewal = renew_worker_claim(
            str(run.id),
            worker_id="lease-v31-worker",
            lease_seconds=99999,
        )
        self.assertEqual(renewal["renewed_items"], 0)
        self.assertEqual(renewal["hard_reservation_max_age_seconds"], 14400)

    def test_exact_current_draft_skips_redundant_explicit_reanalysis_before_claim(self):
        notice = self._notice("فراخوان دارای تحلیل معتبر")
        run = self._active_reanalysis_run()
        item = run.items.get(notice=notice)
        self.assertEqual(item.analysis_reason, "explicit_reanalysis")
        self._draft(run, notice, item.notice_content_hash)

        claimed = claim_newest_run_items(str(run.id), worker_id="throughput-worker", limit=1)

        self.assertEqual(claimed, [])
        item.refresh_from_db()
        self.assertEqual(item.status, ProcurementAnalysisRunItem.Status.SKIPPED)
        self.assertEqual(item.analysis_reason, "already_valid_current_analysis")
        self.assertIsNotNone(item.completed_at)

    def test_reanalysis_reconciliation_scan_is_throttled_between_package_claims(self):
        self._notice("فراخوان برای کنترل cadence reconciliation")
        run = self._active_reanalysis_run()

        first_claim = claim_newest_run_items(
            str(run.id),
            worker_id="throttle-worker",
            limit=1,
        )
        self.assertEqual(len(first_claim), 1)
        run.refresh_from_db()
        first_scan = run.metadata.get("last_reanalysis_reconciliation_at")
        self.assertTrue(first_scan)

        repeated_slice = claim_newest_run_items(str(run.id), worker_id="throttle-worker", limit=1)
        self.assertEqual([item.id for item in repeated_slice], [item.id for item in first_claim])
        run.refresh_from_db()
        self.assertEqual(run.metadata.get("last_reanalysis_reconciliation_at"), first_scan)

    def test_active_worker_can_renew_lease_without_claiming_more_work(self):
        self._notice("فراخوان برای تمدید lease")
        run = self._active_reanalysis_run()
        claimed = claim_newest_run_items(str(run.id), worker_id="lease-worker", limit=1, lease_seconds=300)
        self.assertEqual(len(claimed), 1)
        old_expiry = claimed[0].claim_expires_at

        renewal = renew_worker_claim(
            str(run.id),
            worker_id="lease-worker",
            lease_seconds=3600,
            actor=self.user.username,
        )

        self.assertEqual(renewal["renewed_items"], 1)
        self.assertFalse(renewal["expired_claims_resurrected"])
        claimed[0].refresh_from_db()
        self.assertGreater(claimed[0].claim_expires_at, old_expiry)
        self.assertEqual(run.items.filter(status=ProcurementAnalysisRunItem.Status.CLAIMED).count(), 1)

    def test_renewal_does_not_resurrect_expired_or_other_worker_claims(self):
        self._notice("فراخوان برای کنترل renewal منقضی")
        run = self._active_reanalysis_run()
        claimed = claim_newest_run_items(str(run.id), worker_id="lease-owner", limit=1, lease_seconds=300)
        self.assertEqual(len(claimed), 1)

        wrong_worker = renew_worker_claim(str(run.id), worker_id="other-worker", lease_seconds=3600)
        self.assertEqual(wrong_worker["renewed_items"], 0)

        run.items.filter(pk=claimed[0].pk).update(claim_expires_at=timezone.now() - timedelta(seconds=1))
        expired = renew_worker_claim(str(run.id), worker_id="lease-owner", lease_seconds=3600)
        self.assertEqual(expired["renewed_items"], 0)
        self.assertFalse(expired["expired_claims_resurrected"])

    def test_human_needs_revision_is_not_skipped(self):
        notice = self._notice("فراخوان نیازمند اصلاح انسانی")
        run = self._active_reanalysis_run()
        item = run.items.get(notice=notice)
        self._draft(
            run,
            notice,
            item.notice_content_hash,
            raw_output={"human_review": {"decision": "needs_revision"}},
        )

        claimed = claim_newest_run_items(str(run.id), worker_id="revision-worker", limit=1)

        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].id, item.id)

    def test_exact_prior_compact_result_skips_reanalysis_without_draft(self):
        notice = self._notice("فراخوان دارای نتیجه compact معتبر")
        prior_run = ProcurementAnalysisRun.objects.create(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            status=ProcurementAnalysisRun.Status.COMPLETED,
            context_snapshot=self.context,
            requested_by=self.user,
            started_at=timezone.now() - timedelta(days=1),
            finished_at=timezone.now() - timedelta(days=1),
        )
        run = self._active_reanalysis_run()
        active_item = run.items.get(notice=notice)
        ProcurementAnalysisRunItem.objects.create(
            run=prior_run,
            notice=notice,
            notice_content_hash=active_item.notice_content_hash,
            context_hash=run.context_snapshot.content_hash,
            status=ProcurementAnalysisRunItem.Status.COMPLETED,
            analysis_reason="never_analyzed",
            result_metadata={"compact_only": True, "score": 5},
            completed_at=timezone.now() - timedelta(days=1),
            sequence=1,
            shard_number=1,
        )

        claimed = claim_newest_run_items(str(run.id), worker_id="compact-worker", limit=1)

        self.assertEqual(claimed, [])
        active_item.refresh_from_db()
        self.assertEqual(active_item.status, ProcurementAnalysisRunItem.Status.SKIPPED)
