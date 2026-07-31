import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Contract
from core.procurement_analysis_bridge_v7 import (
    OPPORTUNITY_ADVANCE_COMMAND,
    OPPORTUNITY_CONVERT_COMMAND,
    OPPORTUNITY_PREFLIGHT_COMMAND,
    OPPORTUNITY_START_COMMAND,
)
from procurement.models import ProcurementNotice
from procurement.models_analysis import (
    AnalysisBatch,
    AnalysisContextSnapshot,
    AnalysisRequest,
    NoticeAnalysisDraft,
)
from procurement.models_codes import ProcurementReferenceSequence
from procurement.models_direct import DirectOpportunity, OpportunityResult


class OpportunityWorkflowAcceptanceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="opportunity-acceptance-admin",
            password="test-password",
            is_staff=True,
        )
        self.regular = user_model.objects.create_user(
            username="opportunity-acceptance-reader",
            password="test-password",
        )
        ProcurementReferenceSequence.objects.update_or_create(
            key=ProcurementReferenceSequence.Key.DIRECT,
            defaults={"next_value": 10000},
        )
        AnalysisContextSnapshot.objects.update(status=AnalysisContextSnapshot.Status.RETIRED)
        self.context = AnalysisContextSnapshot.objects.create(
            version=9201,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="Senior procurement analyst",
            base_instructions="Use only supplied facts.",
            analysis_prompt="Assess fit and risk.",
            company_profile={"name": "PDP"},
            qualifications=["educational architecture", "MEP"],
            keywords={"active": ["school", "design", "supervision"]},
            experience_summary=["educational building design"],
            component_versions={"test": 7},
            changed_components=["test"],
            activated_by=self.staff,
        )
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="School building professional services",
            employer_name="Test education authority",
            province="Tehran",
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_CHATGPT,
            status=AnalysisRequest.Status.COMPLETED,
            context_snapshot=self.context,
            requested_by=self.staff,
        )
        self.batch = AnalysisBatch.objects.create(
            request=self.request_record,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.COMPLETED,
            item_count=1,
            completed_count=1,
        )
        self.draft = NoticeAnalysisDraft.objects.create(
            notice=self.notice,
            batch=self.batch,
            context_snapshot=self.context,
            notice_content_hash="a" * 64,
            is_recommended=True,
            score=70,
            priority=NoticeAnalysisDraft.Priority.URGENT,
            fit_for_pdp="Potential educational architecture fit.",
            category="educational building services",
            reason="The scope may match PDP qualifications.",
            recommended_action="Human document review.",
            confidence=62,
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
        )
        self.client = APIClient()
        self.url = reverse("analysisreport-list")

    def _post(self, user, title, payload):
        self.client.force_authenticate(user=user)
        return self.client.post(
            self.url,
            {"title": title, "summary": json.dumps(payload), "source_record_ids": []},
            format="json",
        )

    def test_full_trial_flow_creates_only_a_draft_contract(self):
        preflight = self._post(
            self.staff,
            OPPORTUNITY_PREFLIGHT_COMMAND,
            {"analysis_draft_id": str(self.draft.id)},
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertTrue(preflight.data["ready"])

        start = self._post(
            self.staff,
            OPPORTUNITY_START_COMMAND,
            {"analysis_draft_id": str(self.draft.id)},
        )
        self.assertEqual(start.status_code, 200)
        opportunity_id = start.data["opportunity"]["id"]
        self.assertEqual(start.data["opportunity"]["stage"], DirectOpportunity.Stage.SELECTED)
        self.assertTrue(start.data["trial_record"])

        for stage in [
            DirectOpportunity.Stage.PREPARING,
            DirectOpportunity.Stage.SUBMITTED,
            DirectOpportunity.Stage.WON,
        ]:
            response = self._post(
                self.staff,
                OPPORTUNITY_ADVANCE_COMMAND,
                {"opportunity_id": opportunity_id, "stage": stage},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["opportunity"]["stage"], stage)

        converted = self._post(
            self.staff,
            OPPORTUNITY_CONVERT_COMMAND,
            {"opportunity_id": opportunity_id},
        )
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(
            converted.data["opportunity"]["stage"],
            DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
        )
        self.assertEqual(converted.data["contract"]["status"], Contract.Status.DRAFT)
        self.assertTrue(converted.data["contract_is_draft"])
        self.assertTrue(converted.data["requires_human_review"])

        opportunity = DirectOpportunity.objects.get(pk=opportunity_id)
        result = OpportunityResult.objects.get(opportunity=opportunity)
        contract = Contract.objects.get(pk=result.contract_id)
        self.assertEqual(contract.status, Contract.Status.DRAFT)
        self.assertTrue(contract.code.startswith("TRIAL-"))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.review_status, NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)

    def test_invalid_transition_is_rejected(self):
        start = self._post(
            self.staff,
            OPPORTUNITY_START_COMMAND,
            {"analysis_draft_id": str(self.draft.id)},
        )
        opportunity_id = start.data["opportunity"]["id"]
        invalid = self._post(
            self.staff,
            OPPORTUNITY_ADVANCE_COMMAND,
            {"opportunity_id": opportunity_id, "stage": DirectOpportunity.Stage.WON},
        )
        self.assertEqual(invalid.status_code, 409)
        self.assertEqual(Contract.objects.count(), 0)

    def test_non_staff_user_is_denied(self):
        response = self._post(
            self.regular,
            OPPORTUNITY_START_COMMAND,
            {"analysis_draft_id": str(self.draft.id)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DirectOpportunity.objects.count(), 0)
