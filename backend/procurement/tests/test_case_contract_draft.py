from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent, Contract, Receivable
from procurement.models import ProcurementCase, ProcurementNotice


class CaseContractDraftTests(APITestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(username="contract-manager", password="pass", is_staff=True)
        self.viewer = get_user_model().objects.create_user(username="contract-viewer", password="pass")
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="خدمات طراحی ساختمان اداری",
            employer_name="کارفرمای قرارداد آزمون",
            estimated_amount_rials=123000000,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.case = ProcurementCase.objects.create(
            notice=self.notice,
            stage=ProcurementCase.Stage.WON,
            responsible=self.manager,
            created_by=self.manager,
        )

    def test_preview_does_not_write(self):
        before = Contract.objects.count()
        response = self.client.get(f"/api/v1/procurement/cases/{self.case.id}/contract-preview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["eligible"])
        self.assertEqual(response.data["proposal"]["status"], Contract.Status.DRAFT)
        self.assertFalse(response.data["creates_financial_records"])
        self.assertEqual(Contract.objects.count(), before)

    def test_confirmation_and_won_stage_are_required(self):
        missing_confirmation = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/contract-draft/", {}, format="json"
        )
        self.assertEqual(missing_confirmation.status_code, 400)
        self.case.stage = ProcurementCase.Stage.LOST
        self.case.save(update_fields=["stage", "updated_at"])
        invalid_stage = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/contract-draft/",
            {"confirmed": True},
            format="json",
        )
        self.assertEqual(invalid_stage.status_code, 409)

    def test_create_is_draft_idempotent_and_finance_free(self):
        receivables_before = Receivable.objects.count()
        payload = {
            "confirmed": True,
            "title": "قرارداد طراحی ساختمان اداری",
            "employer": "کارفرمای قرارداد آزمون",
            "field": "معماری",
            "value_rials": "123000000",
        }
        created = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/contract-draft/", payload, format="json"
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["created"])
        self.assertEqual(created.data["contract"]["status"], Contract.Status.DRAFT)
        self.assertFalse(created.data["financial_records_created"])

        repeated = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/contract-draft/", payload, format="json"
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertFalse(repeated.data["created"])
        self.assertEqual(Contract.objects.filter(code=created.data["contract"]["code"]).count(), 1)
        self.assertEqual(Receivable.objects.count(), receivables_before)
        self.assertTrue(AuditEvent.objects.filter(action="procurement.case.create_contract_draft").exists())

    def test_non_staff_cannot_create(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/contract-draft/",
            {"confirmed": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
