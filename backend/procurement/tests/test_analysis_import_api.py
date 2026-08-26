from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from core.models import Contract, Receivable
from procurement.analysis_run_service import (
    claim_run_items,
    create_or_resume_run,
    initialize_run,
)
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisRun
from procurement.opportunity_types import CONSTRUCTION, HUMAN_SOURCE


class ProcurementAnalysisImportApiTests(APITransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chatgpt-service",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.context = AnalysisContextSnapshot.objects.create(
            version=901,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر آزمون",
            base_instructions="نتیجه فقط AI Draft است.",
            analysis_prompt="فراخوان را تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری"],
            keywords={"active": ["مطالعات"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 901},
        )
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="فراخوان آزمون API Import",
            description="خدمات مشاوره، مطالعات و طراحی",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        self.run = initialize_run(str(run.id), actor=self.user.username)
        self.item = claim_run_items(str(self.run.id), worker_id="api-transaction-test", limit=1)[0]
        self.url = f"/api/v1/procurement/analysis/runs/{self.run.id}/results/import/"

    def result_payload(self):
        return {
            "run_item_id": str(self.item.id),
            "claim_token": str(self.item.claim_token),
            "notice_id": str(self.item.notice_id),
            "notice_content_hash": self.item.notice_content_hash,
            "context_hash": self.run.context_snapshot.content_hash,
            "is_recommended": True,
            "score": 88,
            "priority": "high",
            "urgency": "high",
            "fit_for_pdp": "متناسب با خدمات مشاوره",
            "category": "مطالعات و طراحی",
            "business_opportunity_type": "consulting",
            "business_opportunity_type_confidence": 94,
            "business_opportunity_type_reason": "دامنه اصلی خدمات مشاوره است.",
            "reason": "تناسب موضوع با صلاحیت شرکت",
            "recommended_action": "بازبینی انسانی اسناد",
            "matched_qualifications": ["معماری"],
            "matched_experience": ["مطالعات"],
            "risk_notes": ["مهلت کنترل شود"],
            "missing_information": [],
            "confidence": 91,
            "analysis_mode": "deep",
            "screening_reason": "potential_match",
            "model_label": "ChatGPT API transaction test",
        }

    def test_dry_run_and_real_import_work_outside_django_testcase_transaction(self):
        contracts_before = Contract.objects.count()
        receivables_before = Receivable.objects.count()

        dry_response = self.client.post(
            self.url,
            {"results": [self.result_payload()], "dry_run": True},
            format="json",
        )
        self.assertEqual(dry_response.status_code, 201, dry_response.data)
        self.assertEqual(dry_response.data["import"]["counts"]["imported"], 1)
        self.assertTrue(dry_response.data["import"]["dry_run"])
        self.assertEqual(NoticeAnalysisDraft.objects.count(), 0)

        real_response = self.client.post(
            self.url,
            {"results": [self.result_payload()], "dry_run": False},
            format="json",
        )
        self.assertEqual(real_response.status_code, 201, real_response.data)
        self.assertEqual(real_response.data["import"]["counts"]["imported"], 1)

        draft = NoticeAnalysisDraft.objects.get(notice=self.notice)
        self.assertEqual(draft.review_status, NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)
        self.assertTrue(draft.raw_output["decision_is_draft"])
        self.assertTrue(draft.raw_output["requires_human_review"])
        self.assertEqual(draft.business_opportunity_type, "consulting")
        self.assertEqual(draft.raw_output["business_opportunity_type"], "consulting")
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.business_opportunity_type, "consulting")
        self.assertEqual(self.notice.business_opportunity_type_source, "ai_draft")
        self.assertEqual(Contract.objects.count(), contracts_before)
        self.assertEqual(Receivable.objects.count(), receivables_before)

    def test_human_type_change_invalidates_claim_and_is_not_overwritten(self):
        self.notice.business_opportunity_type = CONSTRUCTION
        self.notice.business_opportunity_type_source = HUMAN_SOURCE
        self.notice.business_opportunity_type_reason = "تأیید انسانی پیش از تحلیل"
        self.notice.save(update_fields=[
            "business_opportunity_type", "business_opportunity_type_source",
            "business_opportunity_type_reason", "updated_at",
        ])

        response = self.client.post(
            self.url,
            {"results": [self.result_payload()], "dry_run": False},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(NoticeAnalysisDraft.objects.filter(notice=self.notice).exists())
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.business_opportunity_type, CONSTRUCTION)
        self.assertEqual(self.notice.business_opportunity_type_source, HUMAN_SOURCE)
        self.assertEqual(self.notice.business_opportunity_type_reason, "تأیید انسانی پیش از تحلیل")

    def test_invalid_explicit_type_cannot_enter_recommended_feed(self):
        payload = self.result_payload()
        payload["business_opportunity_type"] = "invalid-type"
        response = self.client.post(
            self.url,
            {"results": [payload], "dry_run": False},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        draft = NoticeAnalysisDraft.objects.get(notice=self.notice)
        self.assertEqual(draft.business_opportunity_type, "unclassified")
        self.assertFalse(draft.is_recommended)
        self.assertLessEqual(draft.score, 59)
        self.notice.refresh_from_db()
        self.assertFalse(self.notice.is_recommended)
