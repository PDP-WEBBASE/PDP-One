from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.analysis_utils import notice_basis_hash
from procurement.models import (
    NoticeSourceLink,
    ProcurementConnector,
    ProcurementNotice,
    SourceNotice,
)
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)
from procurement.models_extraction import ExtractionRun


class AnalysisWorkflowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="analyst", password="test-pass")
        self.client.force_authenticate(self.user)
        self.connector = ProcurementConnector.objects.select_related("source").get(key="hezareh_tenders")
        now = timezone.now()
        self.source_notice = SourceNotice.objects.create(
            connector=self.connector,
            source_record_id="test-analysis-1",
            source_url="https://www.hezarehinfo.net/tenders/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/tenders/nidtest-analysis-1",
            source_declared_type=ProcurementConnector.NoticeType.TENDER,
            title_raw="مطالعات امکان سنجی نمونه",
            employer_raw="کارفرمای نمونه",
            content_hash="a" * 64,
            raw_payload={"title": "مطالعات امکان سنجی نمونه"},
            first_seen_at=now,
            last_seen_at=now,
        )
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مطالعات امکان سنجی نمونه",
            normalized_title="مطالعات امکان سنجی نمونه",
            employer_name="کارفرمای نمونه",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )
        NoticeSourceLink.objects.create(
            procurement_notice=self.notice,
            source_notice=self.source_notice,
            match_type=NoticeSourceLink.MatchType.EXACT,
            confidence=100,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=1,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر ارشد مناقصات و استعلامات شرکت PDP",
            base_instructions="کلیدواژه‌ها زمینه تحلیل هستند و امتیازدهی جبری ممنوع است.",
            company_profile={"name": "مهندسین مشاور طرح و برنامه پارس"},
            qualifications=["معماری", "شهرسازی", "تاسیسات"],
            keywords={"active": ["امکان سنجی", "شهرسازی"]},
            experience_summary=[{"title": "مطالعات امکان سنجی"}],
            component_versions={"role": 1, "keywords": 1, "company_profile": 1},
            changed_components=["initial"],
        )
        self.run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.MANUAL,
            status=ExtractionRun.Status.SUCCEEDED,
            requested_by=self.user,
            started_at=now,
            finished_at=now,
            records_new=1,
        )
        self.run.connectors.add(self.connector)

    def test_manifest_is_lightweight_and_version_aware(self):
        response = self.client.get("/api/v1/procurement/analysis/context/manifest/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["context_version"], 1)
        self.assertTrue(response.data["changed"])
        self.assertNotIn("role_text", response.data)

        unchanged = self.client.get("/api/v1/procurement/analysis/context/manifest/?known_version=1")
        self.assertEqual(unchanged.status_code, 200)
        self.assertFalse(unchanged.data["changed"])
        self.assertEqual(unchanged.data["changed_components"], [])

    def test_manual_request_uses_pdp_command_and_active_context(self):
        response = self.client.post(
            "/api/v1/procurement/analysis-requests/",
            {"trigger": AnalysisRequest.Trigger.MANUAL_WEB, "extraction_run": str(self.run.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["command"], "PDP")
        self.assertEqual(response.data["context_version"], 1)
        self.assertEqual(response.data["status"], AnalysisRequest.Status.PENDING)

    def test_queue_excludes_notice_after_same_basis_is_analyzed(self):
        queued = self.client.get("/api/v1/procurement/analysis/queue/?limit=20")
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(queued.data["count"], 1)
        self.assertEqual(queued.data["items"][0]["id"], str(self.notice.id))

        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_CHATGPT,
            command="PDP",
            status=AnalysisRequest.Status.PROCESSING,
            extraction_run=self.run,
            context_snapshot=self.context,
            requested_by=self.user,
        )
        batch = AnalysisBatch.objects.create(
            request=request_record,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.PROCESSING,
            sequence=1,
            item_count=1,
        )
        NoticeAnalysisDraft.objects.create(
            notice=self.notice,
            batch=batch,
            context_snapshot=self.context,
            notice_content_hash=notice_basis_hash(self.notice),
            is_recommended=True,
            score=88,
            priority=NoticeAnalysisDraft.Priority.HIGH,
            fit_for_pdp="تناسب قوی با سوابق امکان سنجی",
            reason="موضوع با صلاحیت و تجربه شرکت هم راستا است.",
            recommended_action="بررسی فوری اسناد و شرایط احراز",
            confidence=91,
        )

        empty = self.client.get("/api/v1/procurement/analysis/queue/?limit=20")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data["count"], 0)

    def test_chatgpt_can_create_draft_and_not_final_decision(self):
        request_response = self.client.post(
            "/api/v1/procurement/analysis-requests/",
            {"trigger": AnalysisRequest.Trigger.MANUAL_WEB, "extraction_run": str(self.run.id)},
            format="json",
        )
        batch_response = self.client.post(
            "/api/v1/procurement/analysis-batches/",
            {"request": request_response.data["id"], "item_count": 1},
            format="json",
        )
        self.assertEqual(batch_response.status_code, 201)

        draft_response = self.client.post(
            "/api/v1/procurement/analysis-drafts/",
            {
                "notice": str(self.notice.id),
                "batch": batch_response.data["id"],
                "is_recommended": True,
                "score": 92,
                "priority": NoticeAnalysisDraft.Priority.URGENT,
                "fit_for_pdp": "تناسب بسیار خوب با خدمات مشاوره شرکت",
                "category": "امکان سنجی",
                "reason": "صلاحیت و سابقه مرتبط وجود دارد.",
                "recommended_action": "دریافت و بررسی اسناد",
                "matched_experience": [{"title": "مطالعات امکان سنجی"}],
                "risk_notes": ["مهلت کوتاه"],
                "confidence": "93.00",
                "raw_output": {"isRecommended": True},
            },
            format="json",
        )
        self.assertEqual(draft_response.status_code, 201)
        self.assertEqual(draft_response.data["review_status"], NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)
        self.notice.refresh_from_db()
        self.assertTrue(self.notice.is_recommended)
        self.assertFalse(hasattr(self.notice, "case"))
