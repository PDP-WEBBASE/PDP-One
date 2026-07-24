from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_direct import DirectOpportunity


class ProcurementReferenceCodeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="code-user", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _notice(self, kind, title):
        return ProcurementNotice.objects.create(
            resolved_notice_type=kind,
            title=title,
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )

    def test_codes_are_not_assigned_in_all_or_recommended(self):
        tender = self._notice(ProcurementNotice.NoticeType.TENDER, "Tender one")
        inquiry = self._notice(ProcurementNotice.NoticeType.INQUIRY, "Inquiry one")
        inquiry.is_recommended = True
        inquiry.save(update_fields=["is_recommended", "updated_at"])
        direct = DirectOpportunity.objects.create(
            title="Direct one",
            employer_name="Employer",
            next_action="",
            stage=DirectOpportunity.Stage.REVIEWING,
        )

        self.assertFalse(hasattr(tender, "reference_record"))
        self.assertFalse(hasattr(inquiry, "reference_record"))
        self.assertFalse(hasattr(direct, "reference_record"))

        response = self.client.get("/api/v1/procurement/tenders/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertIsNone(results[0]["reference_code"])

    def test_separate_sequences_start_when_selected(self):
        tender = self._notice(ProcurementNotice.NoticeType.TENDER, "Tender selected")
        inquiry = self._notice(ProcurementNotice.NoticeType.INQUIRY, "Inquiry selected")
        direct = DirectOpportunity.objects.create(
            title="Direct selected",
            employer_name="Employer",
            next_action="",
            stage=DirectOpportunity.Stage.REVIEWING,
        )

        ProcurementCase.objects.create(notice=tender, stage=ProcurementCase.Stage.SELECTED)
        ProcurementCase.objects.create(notice=inquiry, stage=ProcurementCase.Stage.SELECTED)
        direct.stage = DirectOpportunity.Stage.SELECTED
        direct.save(update_fields=["stage", "updated_at"])

        self.assertEqual(tender.reference_record.code, "TND-10000")
        self.assertEqual(inquiry.reference_record.code, "INQ-10000")
        self.assertEqual(direct.reference_record.code, "DIR-10000")

    def test_codes_increment_persist_and_are_searchable(self):
        first = self._notice(ProcurementNotice.NoticeType.TENDER, "Tender first")
        second = self._notice(ProcurementNotice.NoticeType.TENDER, "Tender second")

        ProcurementCase.objects.create(notice=first, stage=ProcurementCase.Stage.SELECTED)
        second_case = ProcurementCase.objects.create(notice=second, stage=ProcurementCase.Stage.SELECTED)

        self.assertEqual(first.reference_record.code, "TND-10000")
        self.assertEqual(second.reference_record.code, "TND-10001")

        second_case.stage = ProcurementCase.Stage.SUBMITTED
        second_case.save(update_fields=["stage", "updated_at"])
        second.refresh_from_db()
        self.assertEqual(second.reference_record.code, "TND-10001")

        response = self.client.get("/api/v1/procurement/tenders/?search=TND-10001")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["reference_code"], "TND-10001")
