import tempfile
from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from procurement.analysis_run_service import create_or_resume_run, initialize_run
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class ProcurementMegaBatchBenchmarkTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.temp.cleanup)

        self.user = get_user_model().objects.create_user(
            username="megabatch-manager",
            password="test-pass",
            is_staff=True,
        )
        self.context = AnalysisContextSnapshot.objects.create(
            version=156,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مناقصات",
            base_instructions="همه نتایج فقط AI Draft هستند.",
            analysis_prompt="فراخوان‌ها را بر اساس تناسب با PDP تحلیل کن.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "شهرسازی"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "مطالعات"}],
            component_versions={"snapshot": 156},
        )
        now = timezone.now()
        self.notices = [
            ProcurementNotice.objects.create(
                resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
                title="مطالعات و طراحی پروژه شهری",
                description="خدمات مهندسین مشاور برای مطالعات و طراحی",
                employer_name="کارفرمای اول",
                province="تهران",
                processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
                first_seen_at=now - timedelta(minutes=2),
                last_seen_at=now - timedelta(minutes=2),
                published_date=now.date(),
            ),
            ProcurementNotice.objects.create(
                resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
                title="خرید کالای مصرفی",
                description="خرید صرف کالا",
                employer_name="کارفرمای دوم",
                province="تهران",
                processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
                first_seen_at=now - timedelta(minutes=1),
                last_seen_at=now - timedelta(minutes=1),
                published_date=now.date(),
            ),
        ]
        self.run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.FULL_PENDING,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_WEB,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        self.run = initialize_run(str(self.run.id), actor=self.user.username)
        self.client.force_login(self.user)

    def _start(self):
        response = self.client.post(
            reverse("analysis-megabatch-benchmark-start"),
            {"run_id": str(self.run.id), "corpus_size": 2},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["benchmark"]

    def _batch(self, benchmark_id, stage_size):
        response = self.client.get(
            reverse("analysis-megabatch-benchmark-batch", args=[benchmark_id]),
            {"stage_size": stage_size, "offset": 0},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["batch"]

    def _results(self, batch, recommended_first=True):
        values = []
        for index, item in enumerate(batch["items"]):
            recommended = bool(index == 0 and recommended_first)
            values.append(
                {
                    "i": item["i"],
                    "n": item["n"],
                    "c": item["c"],
                    "x": batch["context"]["hash"],
                    "r": recommended,
                    "s": 85 if recommended else 20,
                    "p": "high" if recommended else "normal",
                    "rs": "مرتبط با خدمات مشاوره" if recommended else "خرید صرف کالا",
                    "a": "بررسی شود" if recommended else "اقدامی لازم نیست",
                    "cf": 95,
                    "mi": [],
                }
            )
        return values

    def test_benchmark_uses_fixed_corpus_without_mutating_production_claims(self):
        initial = list(
            self.run.items.order_by("sequence").values_list(
                "id", "status", "claim_token", "claimed_by", "attempts"
            )
        )
        benchmark = self._start()
        batch = self._batch(benchmark["benchmark_id"], 50)

        self.assertEqual(batch["count"], 2)
        self.assertEqual(batch["corpus_sha256"], benchmark["corpus_sha256"])
        self.assertFalse(batch["production_mutation"])
        self.assertTrue(all("k" not in item for item in batch["items"]))

        after = list(
            self.run.items.order_by("sequence").values_list(
                "id", "status", "claim_token", "claimed_by", "attempts"
            )
        )
        self.assertEqual(after, initial)

    def test_benchmark_compares_recommendation_count_and_exact_set(self):
        benchmark = self._start()
        benchmark_id = benchmark["benchmark_id"]

        baseline = self._batch(benchmark_id, 50)
        response = self.client.post(
            reverse("analysis-megabatch-benchmark-submit", args=[benchmark_id]),
            {
                "stage_size": 50,
                "offset": 0,
                "results": self._results(baseline, recommended_first=True),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["stage"]["complete"])
        self.assertEqual(response.json()["stage"]["recommended"], 1)

        candidate = self._batch(benchmark_id, 250)
        response = self.client.post(
            reverse("analysis-megabatch-benchmark-submit", args=[benchmark_id]),
            {
                "stage_size": 250,
                "offset": 0,
                "results": self._results(candidate, recommended_first=False),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        status_response = self.client.get(
            reverse("analysis-megabatch-benchmark-status", args=[benchmark_id])
        )
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()["benchmark"]
        comparison = status_payload["comparisons_to_50"]["250"]
        self.assertEqual(comparison["baseline_recommended"], 1)
        self.assertEqual(comparison["candidate_recommended"], 0)
        self.assertEqual(comparison["recommendation_drift_count"], 1)
        self.assertEqual(len(comparison["recommendation_removed_ids"]), 1)

    def test_submit_rejects_missing_records(self):
        benchmark = self._start()
        batch = self._batch(benchmark["benchmark_id"], 50)
        response = self.client.post(
            reverse("analysis-megabatch-benchmark-submit", args=[benchmark["benchmark_id"]]),
            {
                "stage_size": 50,
                "offset": 0,
                "results": self._results(batch)[:1],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("تعداد نتایج", response.json()["detail"])


    def test_corpus_build_is_bounded_resumable_and_keeps_one_benchmark_id(self):
        with patch("procurement.analysis_megabatch_benchmark.BUILD_COLLECT_TARGET", 1), patch(
            "procurement.analysis_megabatch_benchmark.BUILD_SCAN_LIMIT", 2
        ):
            first_response = self.client.post(
                reverse("analysis-megabatch-benchmark-start"),
                {"run_id": str(self.run.id), "corpus_size": 2},
                content_type="application/json",
            )
            self.assertEqual(first_response.status_code, 201)
            first = first_response.json()["benchmark"]
            self.assertEqual(first["status"], "preparing")
            self.assertFalse(first["ready"])
            self.assertEqual(first["prepared_count"], 1)
            self.assertEqual(first["next_action"], "call_start_again")

            pending_batch = self.client.get(
                reverse("analysis-megabatch-benchmark-batch", args=[first["benchmark_id"]]),
                {"stage_size": 50, "offset": 0},
            )
            self.assertEqual(pending_batch.status_code, 400)
            self.assertIn("هنوز آماده نیست", pending_batch.json()["detail"])

            second_response = self.client.post(
                reverse("analysis-megabatch-benchmark-start"),
                {"run_id": str(self.run.id), "corpus_size": 2},
                content_type="application/json",
            )
            self.assertEqual(second_response.status_code, 201)
            second = second_response.json()["benchmark"]
            self.assertEqual(second["benchmark_id"], first["benchmark_id"])
            self.assertEqual(second["status"], "ready")
            self.assertTrue(second["ready"])
            self.assertEqual(second["prepared_count"], 2)
            self.assertTrue(second["corpus_sha256"])

    def test_ready_corpus_is_reused_for_same_run_context_and_size(self):
        first = self._start()
        second = self._start()
        self.assertEqual(second["benchmark_id"], first["benchmark_id"])
        self.assertEqual(second["corpus_sha256"], first["corpus_sha256"])
        self.assertTrue(second["ready"])
