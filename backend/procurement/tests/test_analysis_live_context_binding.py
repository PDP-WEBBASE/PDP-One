from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from procurement import analysis_run_adaptive, analysis_run_service
from procurement.analysis_claim_integrity import LIVE_CONTEXT_BINDING_MODE, sync_run_to_active_context
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class AnalysisLiveContextBindingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chatgpt-service",
            password="test-pass",
            is_staff=True,
        )
        self.context_v1 = self.create_context(2101, AnalysisContextSnapshot.Status.ACTIVE)
        self.notice = self.create_notice("فراخوان مطالعات نسخه اول")
        run, created = analysis_run_service.create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        self.run = analysis_run_service.initialize_run(str(run.id), actor=self.user.username)
        self.item = analysis_run_adaptive.claim_newest_run_items(
            str(self.run.id),
            worker_id="live-context-old-worker",
            limit=1,
            lease_seconds=3600,
        )[0]
        self.item.refresh_from_db()
        self.old_claim_token = self.item.claim_token

    def create_context(self, version: int, status_value: str):
        return AnalysisContextSnapshot.objects.create(
            version=version,
            status=status_value,
            role_text=f"تحلیلگر آزمون نسخه {version}",
            base_instructions="فقط آخرین Context فعال مبنای تحلیل است.",
            analysis_prompt="فراخوان را بر اساس Context فعال تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری"],
            keywords={"active": ["مطالعات", str(version)]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": version},
        )

    def create_notice(self, title: str):
        now = timezone.now()
        return ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            type_resolution_status=ProcurementNotice.TypeResolutionStatus.RESOLVED,
            title=title,
            description="خدمات مشاوره و مطالعات",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )

    def activate_v2(self):
        self.context_v1.status = AnalysisContextSnapshot.Status.RETIRED
        self.context_v1.save(update_fields=["status", "updated_at"])
        self.context_v2 = self.create_context(2102, AnalysisContextSnapshot.Status.ACTIVE)
        return self.context_v2

    def old_result_payload(self):
        return {
            "i": str(self.item.id),
            "k": str(self.old_claim_token),
            "n": str(self.item.notice_id),
            "c": self.item.notice_content_hash,
            "x": self.context_v1.content_hash,
            "r": True,
            "s": 80,
            "p": "high",
            "f": "متناسب",
            "g": "مطالعات",
            "rs": "تطابق",
            "a": "بازبینی انسانی",
            "cf": 90,
            "cd": True,
        }

    def test_next_claim_rebinds_run_and_invalidates_old_context_claim(self):
        context_v2 = self.activate_v2()

        claimed = analysis_run_adaptive.claim_newest_run_items(
            str(self.run.id),
            worker_id="live-context-new-worker",
            limit=1,
            lease_seconds=3600,
        )

        self.assertEqual(len(claimed), 1)
        self.run.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.run.context_snapshot_id, context_v2.id)
        self.assertEqual(self.item.context_hash, context_v2.content_hash)
        self.assertNotEqual(self.item.claim_token, self.old_claim_token)
        self.assertEqual(self.item.claimed_by, "live-context-new-worker")
        self.assertEqual(self.run.metadata["context_binding_mode"], LIVE_CONTEXT_BINDING_MODE)

        serialized = analysis_run_service.serialize_claimed_items(claimed)
        self.assertEqual(serialized["context"]["id"], str(context_v2.id))
        self.assertEqual(serialized["context"]["version"], context_v2.version)
        self.assertEqual(serialized["context"]["hash"], context_v2.content_hash)

    def test_import_after_context_switch_rejects_stale_in_flight_result(self):
        context_v2 = self.activate_v2()

        record = analysis_run_service.import_result_records(
            run_id=str(self.run.id),
            results=[self.old_result_payload()],
            actor=self.user.username,
            dry_run=False,
        )

        self.run.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.run.context_snapshot_id, context_v2.id)
        self.assertEqual(self.item.context_hash, context_v2.content_hash)
        self.assertEqual(self.item.status, ProcurementAnalysisRunItem.Status.RETRY)
        self.assertIsNone(self.item.claim_token)
        self.assertEqual(record.counts["imported"], 0)
        self.assertEqual(record.counts["rejected"], 1)
        self.assertEqual(NoticeAnalysisDraft.objects.filter(notice=self.notice).count(), 0)

    def test_admission_after_context_switch_uses_latest_context(self):
        context_v2 = self.activate_v2()
        new_notice = self.create_notice("فراخوان جدید پس از انتشار Context دوم")

        result = analysis_run_adaptive.admit_newest_pending_items(
            str(self.run.id),
            actor=self.user.username,
        )

        self.assertGreaterEqual(result["admitted"], 1)
        new_item = ProcurementAnalysisRunItem.objects.get(run=self.run, notice=new_notice)
        self.run.refresh_from_db()
        self.assertEqual(self.run.context_snapshot_id, context_v2.id)
        self.assertEqual(new_item.context_hash, context_v2.content_hash)

    def test_completed_history_is_not_rewritten_when_context_changes(self):
        self.item.status = ProcurementAnalysisRunItem.Status.COMPLETED
        self.item.claim_token = None
        self.item.claimed_by = ""
        self.item.claimed_at = None
        self.item.claim_expires_at = None
        self.item.result_metadata = {"context_hash": self.context_v1.content_hash}
        self.item.save()
        old_context_hash = self.item.context_hash
        context_v2 = self.activate_v2()

        sync = sync_run_to_active_context(str(self.run.id), actor=self.user.username)

        self.item.refresh_from_db()
        self.run.refresh_from_db()
        self.assertTrue(sync["changed"])
        self.assertEqual(self.run.context_snapshot_id, context_v2.id)
        self.assertEqual(self.item.status, ProcurementAnalysisRunItem.Status.COMPLETED)
        self.assertEqual(self.item.context_hash, old_context_hash)
        self.assertEqual(self.item.result_metadata["context_hash"], self.context_v1.content_hash)
