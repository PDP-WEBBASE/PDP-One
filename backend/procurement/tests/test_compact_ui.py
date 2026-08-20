from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.models import (
    NoticeSourceLink,
    ProcurementConnector,
    ProcurementNotice,
    ProcurementSource,
    SourceNotice,
)
from procurement.models_analysis import AnalysisBatch, AnalysisContextSnapshot, AnalysisRequest, NoticeAnalysisDraft


class CompactProcurementUiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="compact-ui-manager",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.context = AnalysisContextSnapshot.objects.create(
            version=920,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر",
            base_instructions="خروجی AI پیش‌نویس است.",
            analysis_prompt="تحلیل کن.",
        )
        request_record = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_WEB,
            context_snapshot=self.context,
            requested_by=self.user,
            status=AnalysisRequest.Status.PROCESSING,
        )
        self.batch = AnalysisBatch.objects.create(
            request=request_record,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.PROCESSING,
            sequence=1,
            item_count=10,
        )

    def make_notice(self, title, notice_type=ProcurementNotice.NoticeType.INQUIRY, *, deadline=None, published_date=None):
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=title,
            employer_name="کارفرمای آزمون",
            province="اصفهان",
            published_date=published_date or timezone.localdate(),
            submission_deadline=deadline or self.now + timedelta(days=5),
            processing_status=ProcurementNotice.ProcessingStatus.ANALYZED,
            first_seen_at=self.now,
            last_seen_at=self.now,
        )

    def make_draft(self, notice, token="a", *, recommended=True):
        return NoticeAnalysisDraft.objects.create(
            notice=notice,
            batch=self.batch,
            context_snapshot=self.context,
            notice_content_hash=(token * 64)[:64],
            is_recommended=recommended,
            score=90 if recommended else 20,
            priority=NoticeAnalysisDraft.Priority.HIGH if recommended else NoticeAnalysisDraft.Priority.LOW,
            fit_for_pdp="متناسب" if recommended else "نامتناسب",
            category="آزمون",
            reason="نتیجه آزمون",
            recommended_action="بررسی" if recommended else "عدم پیگیری",
            confidence=90,
            review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
            analyzed_at=self.now,
        )

    def link_source(self, notice, *, key, name, record_id):
        source, _ = ProcurementSource.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "base_url": f"https://{key}.example.com",
            },
        )
        connector = ProcurementConnector.objects.filter(
            source=source,
            notice_type=notice.resolved_notice_type,
        ).first()
        if connector is None:
            connector = ProcurementConnector.objects.create(
                source=source,
                key=f"test_{key}_{notice.resolved_notice_type}",
                notice_type=notice.resolved_notice_type,
                list_url_template=f"https://{key}.example.com/list?page={{page}}",
            )
        source_notice = SourceNotice.objects.create(
            connector=connector,
            source_record_id=record_id,
            source_url=f"https://{key}.example.com/{record_id}",
            detail_url=f"https://{key}.example.com/{record_id}/detail",
            source_declared_type=notice.resolved_notice_type,
            title_raw=notice.title,
            employer_raw=notice.employer_name,
            province_raw=notice.province,
            published_at_raw=str(notice.published_date),
            deadline_raw="",
            content_hash=(key * 64)[:64],
            first_seen_at=self.now,
            last_seen_at=self.now,
        )
        NoticeSourceLink.objects.create(
            procurement_notice=notice,
            source_notice=source_notice,
            match_type=NoticeSourceLink.MatchType.EXACT,
            confidence=100,
        )
        return source

    def test_compact_feed_returns_all_sources_in_requested_priority(self):
        notice = self.make_notice("فراخوان چندمنبعی")
        self.link_source(notice, key="parsnamad", name="پارس‌نماد داده", record_id="p-1")
        hezareh = self.link_source(notice, key="hezareh", name="هزاره", record_id="h-1")
        self.link_source(notice, key="setad", name="ستاد ایران", record_id="s-1")

        response = self.client.get("/api/v1/procurement/ui/notices/?notice_type=inquiry&workflow=recent&page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual([item["key"] for item in row["sources"]], ["setad", "hezareh", "parsnamad"])
        self.assertEqual(row["sources"][0]["key"], "setad")

        filtered = self.client.get(
            "/api/v1/procurement/ui/notices/",
            {
                "notice_type": "inquiry",
                "workflow": "recent",
                "source_name": hezareh.name,
            },
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["source_name"], hezareh.name)
        self.assertEqual(len(filtered.data["results"][0]["sources"]), 3)

    def test_deadline_status_and_published_date_are_server_side_filters(self):
        expired = self.make_notice("منقضی", deadline=self.now - timedelta(days=1), published_date=timezone.localdate() - timedelta(days=1))
        available = self.make_notice("فرصت دارد", deadline=self.now + timedelta(days=10), published_date=timezone.localdate())
        self.assertIsNotNone(expired.id)
        self.assertIsNotNone(available.id)

        response = self.client.get(f"/api/v1/procurement/ui/notices/?notice_type=inquiry&workflow=recent&deadline_status=expired&published_on={timezone.localdate() - timedelta(days=1)}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "منقضی")

    def test_bulk_dismiss_rejects_only_requested_notice_type_and_preserves_notices(self):
        tender = self.make_notice("پیشنهاد مناقصه", ProcurementNotice.NoticeType.TENDER)
        inquiry = self.make_notice("پیشنهاد استعلام", ProcurementNotice.NoticeType.INQUIRY)
        tender_draft = self.make_draft(tender, "t", recommended=True)
        inquiry_draft = self.make_draft(inquiry, "i", recommended=True)
        ProcurementNotice.objects.filter(pk__in=[tender.pk, inquiry.pk]).update(is_recommended=True)

        response = self.client.post(
            "/api/v1/procurement/ui/recommendations/dismiss-bulk/?notice_type=tender",
            {"dismiss_all": True, "reason": "آزمون حذف گروهی"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["dismissed"], 1)
        self.assertFalse(response.data["notice_deleted"])

        tender_draft.refresh_from_db()
        inquiry_draft.refresh_from_db()
        tender.refresh_from_db()
        inquiry.refresh_from_db()
        self.assertEqual(tender_draft.review_status, NoticeAnalysisDraft.ReviewStatus.REJECTED)
        self.assertNotEqual(inquiry_draft.review_status, NoticeAnalysisDraft.ReviewStatus.REJECTED)
        self.assertFalse(tender.is_recommended)
        self.assertTrue(inquiry.is_recommended)
        self.assertTrue(ProcurementNotice.objects.filter(pk=tender.pk).exists())
        self.assertTrue(ProcurementNotice.objects.filter(pk=inquiry.pk).exists())

    def test_dashboard_analysis_remaining_is_not_derived_from_browser_page(self):
        unanalyzed = self.make_notice("بدون تحلیل", ProcurementNotice.NoticeType.TENDER)
        analyzed = self.make_notice("تحلیل شده", ProcurementNotice.NoticeType.INQUIRY)
        self.make_draft(analyzed, "d", recommended=True)
        self.assertIsNotNone(unanalyzed.id)

        response = self.client.get("/api/v1/procurement/ui/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["metrics"]["all_notices"]["total"], 2)
        self.assertEqual(response.data["metrics"]["analysis_remaining"]["total"], 1)
        self.assertEqual(response.data["metrics"]["analysis_remaining"]["tender"], 1)
        self.assertEqual(response.data["metrics"]["recommended"]["inquiry"], 1)
