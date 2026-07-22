from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditEvent
from procurement.models_direct import DirectOpportunity, OpportunityFollowUp, OpportunityResult


class DirectOpportunityApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.expert = User.objects.create_user(username="direct-expert", password="test-pass-123")
        self.manager = User.objects.create_user(
            username="direct-manager",
            password="test-pass-123",
            is_staff=True,
        )
        self.client = APIClient()

    def create_quick_opportunity(self):
        self.client.force_authenticate(self.expert)
        response = self.client.post(
            "/api/v1/procurement/direct-opportunities/",
            {
                "title": "طراحی ساختمان اداری جدید",
                "employer_name": "شرکت شهرک‌های صنعتی",
                "next_action": "تماس با معاون فنی",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return DirectOpportunity.objects.get()

    def test_quick_creation_requires_only_three_business_fields(self):
        before = timezone.now()
        opportunity = self.create_quick_opportunity()
        self.assertEqual(opportunity.opportunity_type, DirectOpportunity.OpportunityType.UNASSIGNED)
        self.assertEqual(opportunity.stage, DirectOpportunity.Stage.NEW)
        self.assertEqual(opportunity.responsible, self.expert)
        self.assertGreaterEqual(opportunity.next_action_due, before + timedelta(hours=23))
        self.assertLessEqual(opportunity.next_action_due, before + timedelta(hours=25))

    def test_opportunity_can_move_to_selected_stage(self):
        opportunity = self.create_quick_opportunity()
        response = self.client.patch(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/",
            {"stage": DirectOpportunity.Stage.SELECTED},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.stage, DirectOpportunity.Stage.SELECTED)

    def test_follow_up_updates_next_action_and_stage(self):
        opportunity = self.create_quick_opportunity()
        next_due = timezone.now() + timedelta(days=3)
        response = self.client.post(
            "/api/v1/procurement/opportunity-follow-ups/",
            {
                "opportunity": str(opportunity.id),
                "follow_up_type": OpportunityFollowUp.FollowUpType.PHONE,
                "summary": "کارفرما درخواست رزومه مرتبط کرد.",
                "next_action": "ارسال رزومه مرتبط",
                "next_action_due": next_due.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.stage, DirectOpportunity.Stage.FOLLOWING_UP)
        self.assertEqual(opportunity.next_action, "ارسال رزومه مرتبط")
        self.assertEqual(OpportunityFollowUp.objects.count(), 1)

    def test_terminal_stage_cannot_be_set_without_result_workflow(self):
        opportunity = self.create_quick_opportunity()
        response = self.client.patch(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/",
            {"stage": DirectOpportunity.Stage.LOST},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("stage", response.data)

    def test_soft_delete_requires_reason_and_keeps_database_record(self):
        opportunity = self.create_quick_opportunity()
        response = self.client.post(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/soft-delete/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/soft-delete/",
            {"reason": "تصمیم مدیریت"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        opportunity.refresh_from_db()
        self.assertIsNotNone(opportunity.soft_deleted_at)
        self.assertTrue(DirectOpportunity.objects.filter(pk=opportunity.pk).exists())
        self.assertFalse(
            DirectOpportunity.objects.filter(soft_deleted_at__isnull=True, pk=opportunity.pk).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="procurement.direct_opportunity.soft_delete",
                target_id=str(opportunity.id),
            ).exists()
        )

    def test_only_manager_can_register_result(self):
        opportunity = self.create_quick_opportunity()
        response = self.client.post(
            "/api/v1/procurement/opportunity-results/",
            {
                "opportunity": str(opportunity.id),
                "outcome": OpportunityResult.Outcome.LOST,
                "reason": "رقیب انتخاب شد",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/v1/procurement/opportunity-results/",
            {
                "opportunity": str(opportunity.id),
                "outcome": OpportunityResult.Outcome.LOST,
                "reason": "رقیب انتخاب شد",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.stage, DirectOpportunity.Stage.LOST)

    def test_contract_conversion_requires_contract_reference(self):
        opportunity = self.create_quick_opportunity()
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/v1/procurement/opportunity-results/",
            {
                "opportunity": str(opportunity.id),
                "outcome": OpportunityResult.Outcome.CONVERTED_TO_CONTRACT,
                "reason": "توافق نهایی انجام شد",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("contract", response.data)

    def test_dashboard_includes_active_direct_opportunities(self):
        self.create_quick_opportunity()
        response = self.client.get("/api/v1/procurement/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["direct_opportunities"]["total"], 1)
        self.assertEqual(response.data["direct_opportunities"]["active"], 1)
