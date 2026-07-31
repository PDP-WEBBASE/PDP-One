import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.utils import NotSupportedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.procurement_analysis_bridge import START_COMMAND
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisBatch, AnalysisContextSnapshot, AnalysisRequest


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

    def _start(self):
        return self.client.post(
            self.url,
            {
                "title": START_COMMAND,
                "summary": json.dumps({"limit": 1}),
                "source_record_ids": [],
            },
            format="json",
        )

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
