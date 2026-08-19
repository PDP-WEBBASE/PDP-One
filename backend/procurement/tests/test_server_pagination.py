from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_analysis import AnalysisBatch, AnalysisContextSnapshot, AnalysisRequest, NoticeAnalysisDraft


class ProcurementServerPaginationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="pagination-user", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = timezone.now()

    def create_notice(self, index, *, notice_type=ProcurementNotice.NoticeType.TENDER, published_days_ago=0):
        return ProcurementNotice.objects.create(
            resolved_notice_type=notice_type,
            title=f"فراخوان {index:03d}",
            employer_name="کارفرمای تست",
            province="تهران",
            published_date=timezone.localdate() - timedelta(days=published_days_ago),
            first_seen_at=self.now - timedelta(minutes=index),
            last_seen_at=self.now - timedelta(minutes=index),
        )

    def test_page_size_is_server_side_and_bounded(self):
        for index in range(130):
            self.create_notice(index)

        response = self.client.get(
            "/api/v1/procurement/tenders/?page=1&page_size=30&ordering=-publication_sort,-last_seen_at,-id"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 130)
        self.assertEqual(len(response.data["results"]), 30)
        self.assertIsNotNone(response.data["next"])

        capped = self.client.get("/api/v1/procurement/tenders/?page_size=500")
        self.assertEqual(capped.status_code, 200)
        self.assertEqual(len(capped.data["results"]), 100)

    def test_recent_days_and_publication_order_are_applied_before_pagination(self):
        newest = self.create_notice(1, published_days_ago=0)
        second = self.create_notice(2, published_days_ago=1)
        self.create_notice(3, published_days_ago=4)

        response = self.client.get(
            "/api/v1/procurement/tenders/?recent_days=3&page_size=30&ordering=-publication_sort,-last_seen_at,-id"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(newest.id), str(second.id)],
        )

    def test_selected_workflow_is_filtered_on_server(self):
        selected = self.create_notice(10)
        ordinary = self.create_notice(11)
        ProcurementCase.objects.create(
            notice=selected,
            stage=ProcurementCase.Stage.SELECTED,
            next_action="بررسی اسناد",
            created_by=self.user,
        )

        response = self.client.get(
            "/api/v1/procurement/tenders/?workflow_view=selected&page_size=50"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(selected.id))
        self.assertNotEqual(response.data["results"][0]["id"], str(ordinary.id))


class RecommendedNoticePaginationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="recommended-pagination", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.context = AnalysisContextSnapshot.objects.create(
            version=9001,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="test role",
            base_instructions="test instructions",
        )
        self.request = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_WEB,
            status=AnalysisRequest.Status.PROCESSING,
            context_snapshot=self.context,
            requested_by=self.user,
        )
        self.batch = AnalysisBatch.objects.create(
            request=self.request,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.PROCESSING,
            sequence=1,
        )

    def notice(self, index):
        return ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title=f"پیشنهاد {index:03d}",
            employer_name="کارفرمای پیشنهادی",
            published_date=timezone.localdate(),
            first_seen_at=self.now,
            last_seen_at=self.now - timedelta(seconds=index),
        )

    def draft(self, notice, *, recommended, rejected=False, analyzed_offset=0, basis_suffix="a"):
        return NoticeAnalysisDraft.objects.create(
            notice=notice,
            batch=self.batch,
            context_snapshot=self.context,
            notice_content_hash=(f"{notice.id.hex}{basis_suffix}" * 3)[:64],
            is_recommended=recommended,
            score=90 if recommended else 20,
            priority=NoticeAnalysisDraft.Priority.HIGH,
            fit_for_pdp="fit",
            reason="reason",
            recommended_action="action",
            confidence=90,
            review_status=(NoticeAnalysisDraft.ReviewStatus.REJECTED if rejected else NoticeAnalysisDraft.ReviewStatus.AI_DRAFT),
            analyzed_at=self.now + timedelta(seconds=analyzed_offset),
        )

    def test_latest_effective_draft_remains_source_of_truth(self):
        accepted = self.notice(1)
        dismissed = self.notice(2)
        changed = self.notice(3)
        self.draft(accepted, recommended=True)
        self.draft(dismissed, recommended=True, analyzed_offset=-10, basis_suffix="old")
        self.draft(dismissed, recommended=True, rejected=True, analyzed_offset=10, basis_suffix="new")
        self.draft(changed, recommended=True, analyzed_offset=-10, basis_suffix="old")
        self.draft(changed, recommended=False, analyzed_offset=10, basis_suffix="new")

        response = self.client.get(
            "/api/v1/procurement/recommended-notices/?resolved_notice_type=tender&page_size=50"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(accepted.id))
        self.assertTrue(response.data["results"][0]["is_recommended"])

    def test_recommended_endpoint_is_paginated(self):
        for index in range(55):
            notice = self.notice(index + 100)
            self.draft(notice, recommended=True, basis_suffix=str(index))

        response = self.client.get(
            "/api/v1/procurement/recommended-notices/?resolved_notice_type=tender&page=1&page_size=30"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 55)
        self.assertEqual(len(response.data["results"]), 30)
        self.assertIsNotNone(response.data["next"])
