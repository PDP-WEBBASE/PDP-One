from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from procurement.analysis_run_service import claim_run_items, create_or_resume_run, initialize_run
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class BulkChatGPTAnalysisTests(APITransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="bulk-chatgpt", password="test", is_staff=True)
        self.client.force_authenticate(self.user)
        self.context = AnalysisContextSnapshot.objects.create(
            version=902,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مستقیم",
            base_instructions="همه رکوردها توسط ChatGPT تحلیل شوند.",
            analysis_prompt="تحلیل حجمی مستقیم انجام بده.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "تأسیسات"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "طراحی و نظارت"}],
            component_versions={"snapshot": 902},
        )
        now = timezone.now()
        for index, title in enumerate([
            "خرید کالای نامرتبط",
            "انتخاب مشاور طراحی و نظارت ساختمان اداری",
        ]):
            ProcurementNotice.objects.create(
                resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
                title=title,
                summary="" if index == 0 else "خدمات مهندسی مشاور",
                description="",
                employer_name="کارفرما",
                province="تهران",
                processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
                first_seen_at=now,
                last_seen_at=now,
            )
        run, _ = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.run = initialize_run(str(run.id), actor=self.user.username)
        self.claim_url = f"/api/v1/procurement/analysis/runs/{self.run.id}/claim/"
        self.import_url = f"/api/v1/procurement/analysis/runs/{self.run.id}/results/import/"

    def test_claim_is_compact_context_is_batch_level_and_empty_fields_are_omitted(self):
        response = self.client.post(self.claim_url, {"limit": 500, "lease_seconds": 3600}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["format"], "pdp-one.compact-claim.v1")
        self.assertEqual(response.data["context"]["hash"], self.context.content_hash)
        self.assertEqual(response.data["count"], 2)
        self.assertNotIn("context_hash", response.data["items"][0])
        self.assertNotIn("d", response.data["items"][0]["b"])
        self.assertNotIn("sh", response.data["items"][0]["b"])
        self.assertLess(response.data["payload_chars"], 10000)

    def test_compact_results_store_all_outcomes_but_create_draft_only_for_material_items(self):
        items = claim_run_items(str(self.run.id), worker_id="bulk-test", limit=500, lease_seconds=3600)
        compact_results = []
        for index, item in enumerate(items):
            compact_results.append({
                "i": str(item.id),
                "k": str(item.claim_token),
                "n": str(item.notice_id),
                "c": item.notice_content_hash,
                "x": self.context.content_hash,
                "r": index == 1,
                "s": 10 if index == 0 else 90,
                "p": "low" if index == 0 else "high",
                "f": "نامرتبط" if index == 0 else "مرتبط با خدمات مشاور",
                "g": "خرید" if index == 0 else "خدمات مشاور",
                "rs": "تناسب ندارد" if index == 0 else "تناسب مستقیم دارد",
                "a": "عدم پیگیری" if index == 0 else "بازبینی اسناد",
                "cf": 95,
                "m": "bulk_direct",
                "sr": "clear_no_match" if index == 0 else "strong_match",
                "cd": index == 1,
            })
        response = self.client.post(self.import_url, {"results": compact_results, "dry_run": False}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        counts = response.data["import"]["counts"]
        self.assertEqual(counts["imported"], 2)
        self.assertEqual(counts["drafts_created"], 1)
        self.assertEqual(counts["compact_results"], 1)
        self.assertEqual(NoticeAnalysisDraft.objects.count(), 1)
        self.assertEqual(ProcurementAnalysisRunItem.objects.filter(status="completed").count(), 2)
        compact_item = ProcurementAnalysisRunItem.objects.get(draft__isnull=True)
        self.assertTrue(compact_item.result_metadata["compact_only"])


    def test_compact_result_is_valid_analysis_for_future_runs(self):
        items = claim_run_items(str(self.run.id), worker_id="reuse-test", limit=500, lease_seconds=3600)
        results = []
        for item in items:
            results.append({
                "i": str(item.id),
                "k": str(item.claim_token),
                "n": str(item.notice_id),
                "c": item.notice_content_hash,
                "x": self.context.content_hash,
                "r": False,
                "s": 5,
                "p": "low",
                "f": "نامرتبط",
                "g": "نامرتبط",
                "rs": "تناسب ندارد",
                "a": "عدم پیگیری",
                "cf": 95,
                "cd": False,
            })
        response = self.client.post(self.import_url, {"results": results}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["import"]["counts"]["compact_results"], 2)
        next_run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        next_run = initialize_run(str(next_run.id), actor=self.user.username)
        self.assertEqual(next_run.items.count(), 0)
