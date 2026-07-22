from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementNotice


class ProcurementDashboardDailyStatsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dashboard-user", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _notice(self, notice_type, first_seen_at, recommended=False):
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=f"{notice_type}-{first_seen_at.isoformat()}",
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
            is_recommended=recommended,
        )

    def test_dashboard_reports_today_and_yesterday_by_type_and_recommendation(self):
        now = timezone.now()
        today = timezone.localdate(now)
        start_today = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )
        start_yesterday = start_today - timedelta(days=1)

        self._notice(ProcurementNotice.NoticeType.TENDER, start_today + timedelta(hours=1), True)
        self._notice(ProcurementNotice.NoticeType.INQUIRY, start_today + timedelta(hours=2), False)
        self._notice(ProcurementNotice.NoticeType.TENDER, start_yesterday + timedelta(hours=1), False)
        self._notice(ProcurementNotice.NoticeType.INQUIRY, start_yesterday + timedelta(hours=2), True)
        self._notice(ProcurementNotice.NoticeType.INQUIRY, start_yesterday - timedelta(hours=2), True)

        response = self.client.get("/api/v1/procurement/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["daily_notices"]["today"],
            {"total": 2, "tenders": 1, "inquiries": 1, "recommended": 1},
        )
        self.assertEqual(
            response.data["daily_notices"]["yesterday"],
            {"total": 2, "tenders": 1, "inquiries": 1, "recommended": 1},
        )
