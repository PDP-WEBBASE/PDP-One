from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.models import NoticeSourceLink, ProcurementConnector, ProcurementNotice, SourceNotice
from procurement.models_analysis import AnalysisContextSnapshot, AnalysisRequest, NoticeAnalysisDraft
from procurement.models_extraction import ExtractionRun, ExtractionRunItem


class ProcurementAnalysisEngineTests(APITestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            username="analysis-manager",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.manager)
        self.context = AnalysisContextSnapshot.objects.create(
            version=31,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر ارشد مناقصات و استعلامات",
            base_instructions="نتیجه فقط پیش‌نویس است.",
            analysis_prompt="تناسب، ریسک و اقدام پیشنهادی را تحلیل کن.",
            company_profile={"name": "مهندسین مشاور طرح و برنامه پارس"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "مطالعات امکان‌سنجی"}],
            component_versions={"snapshot": 31},
        )
        self.connector = ProcurementConnector.objects.select_related("source").get(key="hezareh_tenders")
        now = timezone.now()
        self.source_notice = SourceNotice.objects.create(
            connector=self.connector,
            source_record_id="engine-test-1",
            source_url="https://www.hezarehinfo.net/tenders/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/tenders/engine-test-1",
            source_declared_type=ProcurementConnector.NoticeType.TENDER,
            title_raw="مطالعات امکان سنجی و طراحی شهری",
            employer_raw="کارفرمای نمونه",
            content_hash="e" * 64,
            raw_payload={"title": "مطالعات امکان سنجی و طراحی شهری"},
            first_seen_at=now,
            last_seen_at=now,
        )
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مطالعات امکان سنجی و طراحی شهری",
            normalized_title="مطالعات امکان سنجی و طراحی شهری",
            description="تهیه گزارش فنی، اقتصادی و طراحی مفهومی",
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
        self.run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.MANUAL,
            mode=ExtractionRun.Mode.INCREMENTAL,
            status=ExtractionRun.Status.SUCCEEDED,
            requested_by=self.manager,
            started_at=now,
            finished_at=now,
            records_new=1,
        )
        self.run.connectors.add(self.connector)
        ExtractionRunItem.objects.create(
            run=self.run,
            connector=self.connector,
            source_notice=self.source_notice,
            source_record_id=self.source_notice.source_record_id,
            status=ExtractionRunItem.Status.NEW,
            page_number=1,
            position=1,
        )

    def test_manual_engine_start_work_save_finish_and_review(self):
        started = self.client.post(
            "/api/v1/procurement/analysis/engine/start/",
            {"trigger": AnalysisRequest.Trigger.MANUAL_WEB, "extraction_run": str(self.run.id), "limit": 20},
            format="json",
        )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data["work_count"], 1)
        self.assertTrue(started.data["requires_chatgpt_processing"])
        request_id = started.data["request"]["id"]
        batch_id = started.data["batch"]["id"]

        self.notice.refresh_from_db()
        self.assertEqual(self.notice.processing_status, ProcurementNotice.ProcessingStatus.ANALYSIS_QUEUED)

        work = self.client.get(f"/api/v1/procurement/analysis/engine/requests/{request_id}/work/?limit=10")
        self.assertEqual(work.status_code, 200)
        self.assertEqual(work.data["context"]["version"], 31)
        self.assertEqual(work.data["count"], 1)
        self.assertEqual(work.data["items"][0]["notice_id"], str(self.notice.id))
        self.assertIn("analysis_basis", work.data["items"][0])

        saved = self.client.post(
            "/api/v1/procurement/analysis-drafts/",
            {
                "notice": str(self.notice.id),
                "batch": batch_id,
                "is_recommended": True,
                "score": 91,
                "priority": NoticeAnalysisDraft.Priority.HIGH,
                "fit_for_pdp": "تناسب قوی با خدمات مطالعاتی شرکت",
                "category": "امکان سنجی و طراحی شهری",
                "reason": "موضوع با صلاحیت و سابقه شرکت هم‌راستا است.",
                "recommended_action": "بررسی فوری اسناد و شرایط احراز",
                "matched_experience": ["مطالعات امکان‌سنجی"],
                "risk_notes": ["مهلت کنترل شود"],
                "confidence": "92.00",
                "raw_output": {"engine": "ChatGPT connected app"},
            },
            format="json",
        )
        self.assertEqual(saved.status_code, 201)
        draft_id = saved.data["id"]
        self.assertEqual(saved.data["review_status"], NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)

        finished = self.client.post(
            f"/api/v1/procurement/analysis/engine/requests/{request_id}/finish/",
            {"failed_notice_ids": [], "summary": {"note": "یک مورد تحلیل شد"}},
            format="json",
        )
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.data["request"]["status"], AnalysisRequest.Status.COMPLETED)
        self.assertEqual(finished.data["batch"]["completed_count"], 1)
        self.assertEqual(finished.data["batch"]["failed_count"], 0)

        published = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{draft_id}/review/",
            {"review_status": NoticeAnalysisDraft.ReviewStatus.PUBLISHED},
            format="json",
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.data["review_status"], NoticeAnalysisDraft.ReviewStatus.PUBLISHED)
        self.notice.refresh_from_db()
        self.assertTrue(self.notice.is_recommended)

    def test_second_request_with_same_context_and_basis_has_no_changes(self):
        first = self.client.post(
            "/api/v1/procurement/analysis/engine/start/",
            {"extraction_run": str(self.run.id), "limit": 20},
            format="json",
        )
        request_id = first.data["request"]["id"]
        batch_id = first.data["batch"]["id"]
        self.client.post(
            "/api/v1/procurement/analysis-drafts/",
            {
                "notice": str(self.notice.id),
                "batch": batch_id,
                "is_recommended": False,
                "score": 30,
                "priority": NoticeAnalysisDraft.Priority.LOW,
                "fit_for_pdp": "تناسب محدود",
                "category": "سایر",
                "reason": "شرایط احراز نامرتبط است.",
                "recommended_action": "عدم پیگیری مگر با اطلاعات جدید",
                "matched_experience": [],
                "risk_notes": [],
                "confidence": "80.00",
            },
            format="json",
        )
        self.client.post(
            f"/api/v1/procurement/analysis/engine/requests/{request_id}/finish/",
            {"failed_notice_ids": []},
            format="json",
        )

        second = self.client.post(
            "/api/v1/procurement/analysis/engine/start/",
            {"extraction_run": str(self.run.id), "limit": 20},
            format="json",
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["work_count"], 0)
        self.assertFalse(second.data["requires_chatgpt_processing"])
        self.assertEqual(second.data["request"]["status"], AnalysisRequest.Status.NO_CHANGES)

    def test_non_staff_user_cannot_review_draft(self):
        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_WEB,
            context_snapshot=self.context,
            requested_by=self.manager,
            status=AnalysisRequest.Status.PROCESSING,
        )
        batch = request_record.batches.create(
            context_snapshot=self.context,
            status="processing",
            sequence=1,
            item_count=1,
        )
        draft = NoticeAnalysisDraft.objects.create(
            notice=self.notice,
            batch=batch,
            context_snapshot=self.context,
            notice_content_hash="f" * 64,
            is_recommended=True,
            score=80,
            priority=NoticeAnalysisDraft.Priority.HIGH,
            fit_for_pdp="متناسب",
            reason="دلیل",
            recommended_action="بررسی",
            confidence=90,
        )
        viewer = get_user_model().objects.create_user(username="analysis-viewer", password="test-pass")
        self.client.force_authenticate(viewer)
        response = self.client.post(
            f"/api/v1/procurement/analysis/engine/drafts/{draft.id}/review/",
            {"review_status": NoticeAnalysisDraft.ReviewStatus.PUBLISHED},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
