import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AnalysisReport
from core.procurement_analysis_bridge import (
    ACCEPTANCE_ID,
    FINISH_COMMAND,
    SAVE_COMMAND,
    START_COMMAND,
)
from procurement.models import ProcurementNotice
from procurement.models_analysis import (
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)


class ProcurementAnalysisAcceptanceBridgeTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="acceptance-admin",
            password="test-password",
            is_staff=True,
        )
        self.regular = user_model.objects.create_user(
            username="acceptance-reader",
            password="test-password",
        )
        AnalysisContextSnapshot.objects.update(status=AnalysisContextSnapshot.Status.RETIRED)
        self.context = AnalysisContextSnapshot.objects.create(
            version=9001,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="Senior procurement analyst",
            base_instructions="Use only the supplied procurement facts.",
            analysis_prompt="Assess fit, risk, urgency, and recommended action.",
            company_profile={"name": "PDP"},
            qualifications=["architecture", "mechanical and electrical installations"],
            keywords={"active": ["consulting", "design", "supervision"]},
            experience_summary=["building design and supervision"],
            component_versions={"test": 1},
            changed_components=["test"],
            activated_by=self.staff,
        )
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="Building design and supervision tender",
            employer_name="Test employer",
            province="Tehran",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.url = reverse("analysisreport-list")
        self.client = APIClient()

    def _post(self, user, title, payload, source_record_ids=None):
        self.client.force_authenticate(user=user)
        return self.client.post(
            self.url,
            {
                "title": title,
                "summary": json.dumps(payload),
                "source_record_ids": source_record_ids or [],
            },
            format="json",
        )

    def test_full_reserved_acceptance_flow_creates_only_structured_ai_draft(self):
        start_response = self._post(self.staff, START_COMMAND, {"limit": 1})
        self.assertEqual(start_response.status_code, 201)
        self.assertEqual(start_response.data["operation"], "start")
        self.assertEqual(start_response.data["acceptance_id"], ACCEPTANCE_ID)
        self.assertEqual(start_response.data["count"], 1)
        self.assertEqual(AnalysisReport.objects.count(), 0)
        self.assertEqual(AnalysisRequest.objects.count(), 1)

        request_id = start_response.data["request"]["id"]
        batch_id = start_response.data["batch"]["id"]
        notice_id = start_response.data["items"][0]["notice_id"]
        self.assertEqual(notice_id, str(self.notice.id))

        save_response = self._post(
            self.staff,
            SAVE_COMMAND,
            {
                "acceptance_id": ACCEPTANCE_ID,
                "request_id": request_id,
                "batch_id": batch_id,
                "notice_id": notice_id,
                "is_recommended": True,
                "score": 88,
                "priority": "high",
                "fit_for_pdp": "Strong match with PDP building design and supervision capabilities.",
                "category": "building consultancy",
                "reason": "The scope aligns with active qualifications and prior experience.",
                "recommended_action": "Human reviewer should validate deadlines and tender documents.",
                "matched_experience": ["building design and supervision"],
                "risk_notes": ["Tender documents were not reviewed in this acceptance test."],
                "confidence": 86.5,
            },
            source_record_ids=[notice_id],
        )
        self.assertEqual(save_response.status_code, 201)
        self.assertEqual(save_response.data["operation"], "save")
        self.assertTrue(save_response.data["decision_is_draft"])
        self.assertEqual(NoticeAnalysisDraft.objects.count(), 1)
        draft = NoticeAnalysisDraft.objects.get()
        self.assertEqual(draft.review_status, NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)
        self.assertTrue(draft.is_recommended)
        self.assertEqual(AnalysisReport.objects.count(), 0)

        finish_response = self._post(
            self.staff,
            FINISH_COMMAND,
            {
                "acceptance_id": ACCEPTANCE_ID,
                "request_id": request_id,
                "failed_notice_ids": [],
                "summary_note": "Guarded acceptance bridge integration test completed.",
            },
        )
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.data["operation"], "finish")
        self.assertEqual(finish_response.data["batch"]["completed_count"], 1)
        self.assertEqual(finish_response.data["batch"]["failed_count"], 0)
        self.assertEqual(finish_response.data["request"]["status"], AnalysisRequest.Status.COMPLETED)
        draft.refresh_from_db()
        self.assertEqual(draft.review_status, NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)

    def test_reserved_command_is_denied_for_non_staff_user(self):
        response = self._post(self.regular, START_COMMAND, {"limit": 1})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AnalysisRequest.objects.count(), 0)
        self.assertEqual(AnalysisReport.objects.count(), 0)

    def test_reserved_command_rejects_non_json_summary(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            self.url,
            {
                "title": START_COMMAND,
                "summary": "not-json",
                "source_record_ids": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AnalysisRequest.objects.count(), 0)

    def test_normal_analysis_report_behavior_is_unchanged(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            self.url,
            {
                "title": "Ordinary management analysis",
                "summary": "A normal general analysis draft.",
                "source_record_ids": ["contract-test"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AnalysisReport.objects.count(), 1)
        report = AnalysisReport.objects.get()
        self.assertEqual(report.review_status, AnalysisReport.ReviewStatus.AI_DRAFT)
