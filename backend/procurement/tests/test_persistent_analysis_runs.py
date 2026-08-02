import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Contract, Receivable
from procurement.analysis_run_service import (
    cancel_run,
    claim_run_items,
    create_dataset,
    create_or_resume_run,
    export_dataset,
    import_result_records,
    initialize_run,
    pause_run,
    resume_run,
)
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import (
    ProcurementAnalysisDataset,
    ProcurementAnalysisRun,
    ProcurementAnalysisRunItem,
)


class PersistentProcurementAnalysisRunTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="persistent-analysis-manager",
            password="test-pass",
            is_staff=True,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=81,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر ارشد",
            base_instructions="نتیجه فقط Draft است.",
            analysis_prompt="تمام فراخوان‌ها را بررسی کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 81},
        )
        now = timezone.now()
        self.notices = [
            ProcurementNotice.objects.create(
                resolved_notice_type=(
                    ProcurementNotice.NoticeType.TENDER
                    if index % 2
                    else ProcurementNotice.NoticeType.INQUIRY
                ),
                title=f"فراخوان تحلیل پایدار {index}",
                description="خدمات مشاوره، طراحی و مطالعات",
                employer_name="کارفرمای آزمون",
                province="تهران",
                processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
                first_seen_at=now,
                last_seen_at=now,
            )
            for index in range(65)
        ]

    def _run(self):
        run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        return initialize_run(str(run.id), actor=self.user.username)

    def test_full_pending_run_is_not_limited_to_twenty_or_fifty_records(self):
        run = self._run()
        self.assertEqual(run.status, ProcurementAnalysisRun.Status.RUNNING)
        self.assertEqual(run.items.count(), 65)
        self.assertEqual(run.counters["eligible"], 65)
        self.assertEqual(run.counters["remaining"], 65)
        self.assertEqual(run.analysis_request.batches.get().item_count, 65)

    def test_second_manual_or_scheduled_start_reuses_the_active_run(self):
        run = self._run()
        second, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.SCHEDULED,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor="scheduled-task",
        )
        self.assertFalse(created)
        self.assertEqual(second.id, run.id)
        self.assertEqual(ProcurementAnalysisRun.objects.filter(status__in=ProcurementAnalysisRun.ACTIVE_STATUSES).count(), 1)

    def test_claim_is_atomic_and_import_creates_only_ai_drafts(self):
        run = self._run()
        contracts_before = Contract.objects.count()
        receivables_before = Receivable.objects.count()
        first = claim_run_items(str(run.id), worker_id="worker-1", limit=25)
        second = claim_run_items(str(run.id), worker_id="worker-2", limit=25)
        self.assertEqual(len(first), 25)
        self.assertEqual(len(second), 25)
        self.assertFalse({item.id for item in first} & {item.id for item in second})

        item = first[0]
        result = {
            "run_item_id": str(item.id),
            "claim_token": str(item.claim_token),
            "notice_id": str(item.notice_id),
            "notice_content_hash": item.notice_content_hash,
            "context_hash": run.context_snapshot.content_hash,
            "is_recommended": True,
            "score": 88,
            "priority": "high",
            "urgency": "high",
            "fit_for_pdp": "متناسب با خدمات مشاوره",
            "category": "مطالعات و طراحی",
            "reason": "تناسب موضوع و صلاحیت",
            "recommended_action": "بازبینی انسانی اسناد",
            "matched_qualifications": ["معماری"],
            "matched_experience": ["مطالعات"],
            "risk_notes": ["مهلت کنترل شود"],
            "missing_information": [],
            "confidence": 91,
            "analysis_mode": "deep",
            "screening_reason": "potential_match",
            "model_label": "ChatGPT test",
        }
        imported = import_result_records(
            run_id=str(run.id),
            results=[result],
            actor=self.user.username,
            dry_run=False,
        )
        self.assertEqual(imported.counts["imported"], 1)
        draft = NoticeAnalysisDraft.objects.get(notice_id=item.notice_id)
        self.assertEqual(draft.review_status, NoticeAnalysisDraft.ReviewStatus.AI_DRAFT)
        self.assertTrue(draft.raw_output["decision_is_draft"])
        self.assertTrue(draft.raw_output["requires_human_review"])
        self.assertEqual(Contract.objects.count(), contracts_before)
        self.assertEqual(Receivable.objects.count(), receivables_before)

    def test_pause_resume_and_cancel_preserve_completed_results(self):
        run = self._run()
        paused = pause_run(str(run.id), actor=self.user.username)
        self.assertEqual(paused.status, ProcurementAnalysisRun.Status.PAUSED)
        self.assertEqual(claim_run_items(str(run.id), worker_id="worker", limit=5), [])
        resumed = resume_run(str(run.id), actor=self.user.username)
        self.assertEqual(resumed.status, ProcurementAnalysisRun.Status.RUNNING)
        cancelled = cancel_run(str(run.id), actor=self.user.username)
        self.assertEqual(cancelled.status, ProcurementAnalysisRun.Status.CANCELLED)
        self.assertEqual(
            cancelled.items.exclude(status=ProcurementAnalysisRunItem.Status.CANCELLED).count(),
            0,
        )

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @patch("procurement.analysis_run_service._restore_verify_sql")
    @patch("procurement.analysis_run_service._write_sql_dump")
    def test_dataset_has_sharded_jsonl_csv_manifest_and_sql_validation(self, write_sql, restore_sql):
        run = self._run()

        def make_sql(path: Path):
            path.write_bytes(b"sql")
            return {"created": True}

        write_sql.side_effect = make_sql
        restore_sql.return_value = {"attempted": True, "passed": True, "reason": ""}
        dataset = create_dataset(run, shard_size=25)
        dataset = export_dataset(str(dataset.id), actor=self.user.username)
        self.assertEqual(dataset.status, ProcurementAnalysisDataset.Status.READY)
        self.assertEqual(dataset.record_count, 65)
        self.assertEqual(dataset.shard_count, 3)
        kinds = {item["kind"] for item in dataset.files}
        self.assertEqual(kinds, {"jsonl", "csv", "sql", "manifest"})
        self.assertTrue(dataset.validation["sql_restore"]["passed"])
        manifest_file = next(item for item in dataset.files if item["kind"] == "manifest")
        manifest = json.loads(Path(manifest_file["path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["records_in_files"], 65)
        self.assertEqual(manifest["context_hash"], self.context.content_hash)
