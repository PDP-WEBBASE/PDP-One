from django.test import TestCase
from django.utils import timezone

from procurement.models import ProcurementNotice
from procurement.views_dashboard_read_model import _breakdown, _typed_count_fields


class ProcurementDashboardReadModelTests(TestCase):
    def test_consolidated_type_counts_use_one_aggregate_query(self):
        now = timezone.now()
        ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه آزمون",
            first_seen_at=now,
            last_seen_at=now,
        )
        ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="استعلام آزمون",
            first_seen_at=now,
            last_seen_at=now,
        )
        queryset = ProcurementNotice.objects.filter(soft_deleted_at__isnull=True, is_hidden=False)
        with self.assertNumQueries(1):
            values = queryset.aggregate(
                **_typed_count_fields("all", "resolved_notice_type")
            )
        self.assertEqual(_breakdown(values, "all"), {"total": 2, "tender": 1, "inquiry": 1})
