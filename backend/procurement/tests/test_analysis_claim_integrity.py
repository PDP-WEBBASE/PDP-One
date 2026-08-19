from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from procurement import analysis_run_adaptive, analysis_run_service
from procurement.analysis_claim_integrity import CLAIM_INTEGRITY_KEY
from procurement.analysis_throughput import recent_throughput_snapshot
from procurement.connectors.types import ParsedNotice
from procurement.ingestion import ingest_parsed_notice
from procurement.models import ProcurementConnector, ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisImport, ProcurementAnalysisRun, ProcurementAnalysisRunItem


class AnalysisClaimIntegrityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chatgpt-service",
            password="test-pass",
            is_staff=True,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=1901,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر آزمون",
            base_instructions="نتیجه فقط AI Draft است.",
            analysis_prompt="فراخوان را تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری"],
            keywords={"active": ["مطالعات"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 1901},
        )
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            type_resolution_status=ProcurementNotice.TypeResolutionStatus.RESOLVED,
            title="فراخوان مطالعات و طراحی",
            description="خدمات مشاوره، مطالعات و طراحی",
            employer_name="کارفرمای آزمون",
            province="تهران",
            processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
            first_seen_at=now,
            last_seen_at=now,
        )
        run, created = analysis_run_service.create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        self.run = analysis_run_service.initialize_run(str(run.id), actor=self.user.username)
        self.item = analysis_run_adaptive.claim_newest_run_items(
            str(self.run.id),
            worker_id="claim-integrity-test",
            limit=1,
            lease_seconds=3600,
        )[0]
        self.item.refresh_from_db()
        self.assertIn(CLAIM_INTEGRITY_KEY, self.item.screening)

    def result_payload(self):
        return {
            "i": str(self.item.id),
            "k": str(self.item.claim_token),
            "n": str(self.item.notice_id),
            "c": self.item.notice_content_hash,
            "x": self.run.context_snapshot.content_hash,
            "r": True,
            "s": 88,
            "p": "high",
            "f": "متناسب با خدمات مشاوره",
            "g": "مطالعات و طراحی",
            "rs": "تناسب موضوع با صلاحیت شرکت",
            "a": "بازبینی انسانی اسناد",
            "cf": 91,
            "m": "bulk_direct",
            "sr": "potential_match",
            "cd": True,
        }

    def test_legacy_hash_churn_is_rebased_when_semantic_claim_basis_is_unchanged(self):
        original_item_hash = self.item.notice_content_hash
        self.notice.type_resolution_status = ProcurementNotice.TypeResolutionStatus.NEEDS_REVIEW
        self.notice.save(update_fields=["type_resolution_status", "updated_at"])

        current_legacy_hash = analysis_run_service.notice_basis_hash(self.notice)
        self.assertNotEqual(current_legacy_hash, original_item_hash)

        record = analysis_run_service.import_result_records(
            run_id=str(self.run.id),
            results=[self.result_payload()],
            actor=self.user.username,
            dry_run=False,
        )

        self.assertEqual(record.counts["imported"], 1)
        self.assertEqual(record.counts["invalid_hash"], 0)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ProcurementAnalysisRunItem.Status.COMPLETED)
        self.assertEqual(self.item.notice_content_hash, current_legacy_hash)
        self.assertEqual(NoticeAnalysisDraft.objects.filter(notice=self.notice).count(), 1)

    def test_real_semantic_change_after_claim_is_retried_and_not_imported(self):
        self.notice.title = "فراخوان مطالعات و طراحی ـ اصلاح واقعی"
        self.notice.save(update_fields=["title", "updated_at"])

        record = analysis_run_service.import_result_records(
            run_id=str(self.run.id),
            results=[self.result_payload()],
            actor=self.user.username,
            dry_run=False,
        )

        self.assertEqual(record.counts["imported"], 0)
        self.assertEqual(record.counts["invalid_hash"], 1)
        self.assertEqual(
            record.report["errors"][0]["error"],
            "analysis_basis_changed_after_claim",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ProcurementAnalysisRunItem.Status.RETRY)
        self.assertEqual(self.item.last_error, "notice_changed_after_claim")
        self.assertIsNone(self.item.claim_token)
        self.assertEqual(NoticeAnalysisDraft.objects.filter(notice=self.notice).count(), 0)

    def test_recent_throughput_exposes_exact_error_buckets_and_sampled_classes(self):
        ProcurementAnalysisImport.objects.create(
            run=self.run,
            status=ProcurementAnalysisImport.Status.PARTIAL,
            dry_run=False,
            counts={
                "total": 3,
                "imported": 1,
                "duplicate": 0,
                "rejected": 0,
                "invalid_hash": 2,
                "invalid_context": 0,
                "error": 0,
            },
            report={
                "errors": [
                    {"index": "2", "error": "analysis_basis_changed_after_claim"},
                    {"index": "3", "error": "analysis_basis_changed_after_claim"},
                ],
                "errors_truncated": 0,
            },
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

        snapshot = recent_throughput_snapshot(self.run)
        self.assertGreaterEqual(snapshot["import_error_buckets"]["invalid_hash"], 2)
        self.assertGreaterEqual(
            snapshot["import_error_classes_sampled"]["analysis_basis_changed_after_claim"],
            2,
        )
        self.assertTrue(snapshot["recent_imports"])


class RelativeDeadlineIngestionStabilityTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="hezareh_tenders")

    def parsed_notice(self):
        return ParsedNotice(
            source_record_id="RELATIVE-10950416",
            source_url="https://www.hezarehinfo.net/tenders/-%21/page-1",
            detail_url="https://www.hezarehinfo.net/tenders/nid-relative-10950416",
            source_declared_type="tender",
            content_detected_type="tender",
            type_resolution_status="resolved",
            title="مناقصه طراحی ساختمان با مهلت نسبی",
            province="تهران",
            deadline_raw="۲ روز و ۱۲ ساعت",
            position=1,
        )

    @patch("procurement.dates.timezone.now")
    def test_unchanged_relative_deadline_keeps_first_materialized_absolute_time(self, mocked_now):
        first_now = timezone.make_aware(
            datetime(2026, 8, 19, 9, 0, 0),
            timezone.get_current_timezone(),
        )
        mocked_now.return_value = first_now
        _, notice, first_status = ingest_parsed_notice(self.connector, self.parsed_notice())
        first_deadline = notice.submission_deadline
        self.assertIsNotNone(first_deadline)

        mocked_now.return_value = first_now + timedelta(hours=1)
        _, notice, second_status = ingest_parsed_notice(self.connector, self.parsed_notice())
        notice.refresh_from_db()

        self.assertEqual(first_status, "new")
        self.assertEqual(second_status, "duplicate")
        self.assertEqual(notice.submission_deadline, first_deadline)
        self.assertEqual(
            notice.date_metadata["deadline"].get("stability_source"),
            "preserved_existing_relative_deadline",
        )
