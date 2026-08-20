from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.models import ProcurementNotice


class CompactBrowseDashboardTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="compact-procurement-manager",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.now = timezone.now()

    def make_notice(
        self,
        title,
        *,
        notice_type=ProcurementNotice.NoticeType.TENDER,
        deadline=None,
        published_date=None,
        processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
    ):
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=title,
            employer_name="کارفرمای آزمون",
            province="تهران",
            published_date=published_date,
            submission_deadline=deadline,
            processing_status=processing_status,
            first_seen_at=self.now,
            last_seen_at=self.now,
        )

    @staticmethod
    def response_rows(response):
        return response.data.get("results", response.data)

    def test_deadline_state_and_exact_publication_date_filters(self):
        today = timezone.localdate(self.now)
        yesterday = today - timedelta(days=1)
        expired = self.make_notice("منقضی", deadline=self.now - timedelta(hours=2), published_date=today)
        expiring = self.make_notice("در حال انقضا", deadline=self.now + timedelta(days=2), published_date=yesterday)
        available = self.make_notice("فرصت دارد", deadline=self.now + timedelta(days=6), published_date=yesterday)
        unknown = self.make_notice("مهلت نامشخص", deadline=None, published_date=today)
        self.make_notice(
            "استعلام دیگر",
            notice_type=ProcurementNotice.NoticeType.INQUIRY,
            deadline=self.now + timedelta(days=2),
            published_date=yesterday,
        )

        response = self.client.get("/api/v1/procurement/browse-notices/?resolved_notice_type=tender&deadline_state=expired")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({str(row["id"]) for row in self.response_rows(response)}, {str(expired.id)})

        response = self.client.get("/api/v1/procurement/browse-notices/?resolved_notice_type=tender&deadline_state=expiring")
        self.assertEqual({str(row["id"]) for row in self.response_rows(response)}, {str(expiring.id)})

        response = self.client.get("/api/v1/procurement/browse-notices/?resolved_notice_type=tender&deadline_state=available")
        self.assertEqual({str(row["id"]) for row in self.response_rows(response)}, {str(available.id)})

        response = self.client.get("/api/v1/procurement/browse-notices/?resolved_notice_type=tender&deadline_state=unknown")
        self.assertEqual({str(row["id"]) for row in self.response_rows(response)}, {str(unknown.id)})

        response = self.client.get(
            f"/api/v1/procurement/browse-notices/?resolved_notice_type=tender&published_on={yesterday.isoformat()}"
        )
        self.assertEqual(
            {str(row["id"]) for row in self.response_rows(response)},
            {str(expiring.id), str(available.id)},
        )

    def test_dashboard_returns_database_breakdowns_and_analysis_basis(self):
        today = timezone.localdate(self.now)
        self.make_notice(
            "مناقصه تحلیل‌شده",
            notice_type=ProcurementNotice.NoticeType.TENDER,
            deadline=self.now + timedelta(days=1),
            published_date=today,
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
        )
        self.make_notice(
            "مناقصه تحلیل‌نشده",
            notice_type=ProcurementNotice.NoticeType.TENDER,
            deadline=self.now + timedelta(days=2),
            published_date=today,
        )
        self.make_notice(
            "استعلام تحلیل‌نشده",
            notice_type=ProcurementNotice.NoticeType.INQUIRY,
            deadline=self.now + timedelta(days=5),
            published_date=today,
        )

        response = self.client.get("/api/v1/procurement/pagination-dashboard-metrics/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["analysis_basis"], "processing_status_fallback")
        self.assertEqual(response.data["breakdown"]["notice_total"], {"total": 3, "tender": 2, "inquiry": 1})
        self.assertEqual(response.data["breakdown"]["unanalyzed"], {"total": 2, "tender": 1, "inquiry": 1})
        self.assertEqual(response.data["breakdown"]["new_today"], {"total": 3, "tender": 2, "inquiry": 1})
        self.assertEqual(response.data["breakdown"]["urgent"], {"total": 2, "tender": 2, "inquiry": 0})
