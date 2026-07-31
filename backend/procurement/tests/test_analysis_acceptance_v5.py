import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.utils import NotSupportedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.procurement_analysis_bridge import ACCEPTANCE_ID, FINISH_COMMAND, SAVE_COMMAND, START_COMMAND
from procurement.models import ProcurementNotice
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)


class ProcurementAnalysisAcceptanceV5Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="acceptance-v5-admin",
            password="test-password",
            is_staff=True,
        )
        AnalysisContextSnapshot.objects.update(status=AnalysisContextSnapshot.Status.RETIRED)
        self.context = AnalysisContextSnapshot.objects.create(
            version=9105,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="Senior procurement analyst",
            base_instructions="Use only supplied facts.",
            analysis_prompt="Assess fit and risk.",
            company_profile={"name": "PDP"},
            qualifications=["architecture"],
            keywords={"active": ["design", "supervision"]},
            experience_summary=["building design and supervision"],
            component_versions={"test": 5},
            changed_components=["test"],
            activated_by=self.staff,
        )
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="Architectural design and supervision tender",
            employer_name="Test employer",
            province="Tehran",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)
        self.url = reverse("analysisreport-list")

    def _post(self, title, payload, source_record_ids=None):
        return self.client.post(
            self.url,
            {
                "title": title,
                "summary": json.dumps(payload),
                "source_record_ids": source_record_ids or [],
            },
            format="json",
        )

    def _start(self):
        return self._post(START_COMMAND, {"limit": 1})

    @patch(
        "procurement.analysis_workflow_postgres.start_analysis_request",
        side_effect=NotSupportedError("row locking must not be used by V5"),
    )
    def test_start_bypasses_postgres_row_lock_helper(self, locked_helper):
        response = self._start()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["operation"], "start")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(AnalysisRequest.objects.count(), 1)
        self.assertEqual(AnalysisBatch.objects.count(), 1)
        locked_helper.assert_not_called()

    @patch(
        "procurement.analysis_workflow.collect_work_items",
        side_effect=NotSupportedError("simulated production query limitation"),
    )
    def test_start_failure_rolls_back_request_and_batch(self, collect_work_items):
        response = self._start()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["stage"], "collect-work-items")
        self.assertEqual(response.data["safe_error"], "NotSupportedError")
        self.assertEqual(AnalysisRequest.objects.count(), 0)
        self.assertEqual(AnalysisBatch.objects.count(), 0)
        self.notice.refresh_from_db()
        self.assertEqual(
            self.notice.processing_status,
            ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
        )
        collect_work_items.assert_called_once()

    @patch(
        "procurement.analysis_workflow.finish_analysis_request",
        side_effect=NotSupportedError("row locking must not be used by V6"),
    )
    def test_finish_bypasses_row_lock_helper(self, locked_helper):
        start_response = self._start()
        self.assertEqual(start_response.status_code, 201)
        request_id = start_response.data["request"]["id"]
        batch_id = start_response.data["batch"]["id"]
        notice_id = start_response.data["items"][0]["notice_id"]

        save_response = self._post(
            SAVE_COMMAND,
            {
                "acceptance_id": ACCEPTANCE_ID,
                "request_id": request_id,
                "batch_id": batch_id,
                "notice_id": notice_id,
                "is_recommended": True,
                "score": 80,
                "priority": "high",
                "fit_for_pdp": "The scope matches PDP architectural consulting qualifications.",
                "category": "architectural consulting",
                "reason": "The notice explicitly requests design and supervision services.",
                "recommended_action": "A human reviewer should inspect the full tender documents.",
                "matched_experience": ["building design and supervision"],
                "risk_notes": ["Test data only."],
                "confidence": 90,
            },
            source_record_ids=[notice_id],
        )
        self.assertEqual(save_response.status_code, 201)
        self.assertEqual(NoticeAnalysisDraft.objects.count(), 1)

        finish_response = self._post(
            FINISH_COMMAND,
            {
                "acceptance_id": ACCEPTANCE_ID,
                "request_id": request_id,
                "failed_notice_ids": [],
                "summary_note": "V6 lock-free finish regression test.",
            },
        )
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.data["operation"], "finish")
        self.assertEqual(finish_response.data["request"]["status"], AnalysisRequest.Status.COMPLETED)
        self.assertEqual(finish_response.data["batch"]["completed_count"], 1)
        self.assertEqual(finish_response.data["batch"]["failed_count"], 0)
        locked_helper.assert_not_called()
