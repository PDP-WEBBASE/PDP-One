import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.procurement_analysis_bridge_v8 import OPPORTUNITY_PREFLIGHT_COMMAND
from procurement.models import ProcurementNotice
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)


class OpportunityPreflightMetadataTests(TestCase):
    def test_preflight_returns_recommended_draft_identifier_and_basis(self):
        user = get_user_model().objects.create_user(
            username="opportunity-preflight-admin",
            password="test-password",
            is_staff=True,
        )
        AnalysisContextSnapshot.objects.update(status=AnalysisContextSnapshot.Status.RETIRED)
        context = AnalysisContextSnapshot.objects.create(
            version=9301,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="Procurement analyst",
            base_instructions="Use supplied facts.",
            analysis_prompt="Assess fit.",
            company_profile={"name": "PDP"},
            qualifications=["architecture"],
            keywords={"active": ["school"]},
            experience_summary=["school design"],
            component_versions={"test": 8},
            changed_components=["test"],
            activated_by=user,
        )
        now = timezone.now()
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="Educational building supervision",
            employer_name="Test education authority",
            province="Tehran",
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
            first_seen_at=now,
            last_seen_at=now,
        )
        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_CHATGPT,
            status=AnalysisRequest.Status.COMPLETED,
            context_snapshot=context,
            requested_by=user,
        )
        batch = AnalysisBatch.objects.create(
            request=request_record,
            context_snapshot=context,
            status=AnalysisBatch.Status.COMPLETED,
            item_count=1,
            completed_count=1,
        )
        draft = NoticeAnalysisDraft.objects.create(
            notice=notice,
            batch=batch,
            context_snapshot=context,
            notice_content_hash="b" * 64,
            is_recommended=True,
            score=82,
            priority=NoticeAnalysisDraft.Priority.HIGH,
            fit_for_pdp="Matches educational architecture services.",
            category="educational building services",
            reason="Relevant qualification and experience.",
            recommended_action="Review source documents.",
            confidence=78,
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
        )

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            reverse("analysisreport-list"),
            {
                "title": OPPORTUNITY_PREFLIGHT_COMMAND,
                "summary": json.dumps({"acceptance_id": "opportunity-workflow-acceptance-v1-20260731"}),
                "source_record_ids": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ready"])
        self.assertEqual(response.data["recommended_ai_draft_count"], 1)
        self.assertEqual(len(response.data["recommended_ai_drafts"]), 1)
        item = response.data["recommended_ai_drafts"][0]
        self.assertEqual(item["id"], str(draft.id))
        self.assertEqual(item["notice_id"], str(notice.id))
        self.assertEqual(item["title"], notice.title)
        self.assertEqual(item["score"], 82)
        self.assertEqual(item["review_status"], NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)
