from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementNotice
from procurement.models_direct import DirectOpportunity


class ProcurementReferenceCodeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="code-user", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_separate_sequences_start_at_ten_thousand(self):
        tender = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="Tender one",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        inquiry = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="Inquiry one",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        direct = DirectOpportunity.objects.create(
            title="Direct one",
            employer_name="Employer",
            next_action="",
        )

        self.assertEqual(tender.reference_record.code, "TND-10000")
        self.assertEqual(inquiry.reference_record.code, "INQ-10000")
        self.assertEqual(direct.reference_record.code, "DIR-10000")

    def test_codes_increment_and_are_searchable(self):
        first = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="Tender first",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        second = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="Tender second",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )

        self.assertEqual(first.reference_record.code, "TND-10000")
        self.assertEqual(second.reference_record.code, "TND-10001")

        response = self.client.get("/api/v1/procurement/tenders/?search=TND-10001")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["reference_code"], "TND-10001")
