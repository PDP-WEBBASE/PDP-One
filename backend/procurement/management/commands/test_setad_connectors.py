import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from procurement.models import ProcurementConnector, ProcurementSource, SourceNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


class Command(BaseCommand):
    help = "Run a controlled public-list test for the approved SETAD connectors."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages",
            type=int,
            default=2,
            help="Maximum pages per connector. The safety limit is 5.",
        )
        parser.add_argument(
            "--connector",
            choices=["all", "tenders", "inquiries"],
            default="all",
            help="Select both SETAD connectors or one connector only.",
        )
        parser.add_argument(
            "--report",
            default="",
            help="Optional path for the sanitized JSON report.",
        )

    def handle(self, *args, **options):
        pages = options["pages"]
        if pages < 1 or pages > 5:
            raise CommandError("--pages must be between 1 and 5 for the controlled test.")

        key_map = {
            "all": ["setad_tenders", "setad_inquiries"],
            "tenders": ["setad_tenders"],
            "inquiries": ["setad_inquiries"],
        }
        selected_keys = key_map[options["connector"]]

        source = ProcurementSource.objects.get(key="setad")
        source.enabled = True
        source.status = ProcurementSource.Status.ACTIVE
        configuration = dict(source.configuration or {})
        configuration.update(
            {
                "activation_approved_at": "2026-07-23",
                "last_controlled_test_started_at": timezone.now().isoformat(),
                "details_policy": "public-list-only; no captcha bypass",
            }
        )
        source.configuration = configuration
        source.save(update_fields=["enabled", "status", "configuration", "updated_at"])

        connectors = list(
            ProcurementConnector.objects.filter(key__in=selected_keys)
            .select_related("source")
            .order_by("key")
        )
        if len(connectors) != len(selected_keys):
            raise CommandError("One or more SETAD connectors are missing from the database.")

        for connector in connectors:
            connector.enabled = True
            connector.status = ProcurementConnector.Status.ACTIVE
            connector.save(update_fields=["enabled", "status", "updated_at"])

        run = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.MANUAL,
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            analyze_after_success=False,
            page_cap=pages,
            summary={
                "controlled_live_test": True,
                "public_list_only": True,
                "requested_connector_keys": selected_keys,
            },
        )
        run.connectors.add(*connectors)

        result = run_extraction(str(run.id))
        run.refresh_from_db()

        connector_reports = []
        for connector in connectors:
            samples = list(
                SourceNotice.objects.filter(connector=connector)
                .order_by("-last_seen_at")
                .values(
                    "source_record_id",
                    "title_raw",
                    "employer_raw",
                    "province_raw",
                    "published_at_raw",
                    "deadline_raw",
                    "detail_status",
                )[:5]
            )
            errors = list(
                run.errors.filter(connector=connector)
                .order_by("created_at")
                .values(
                    "category",
                    "safe_message",
                    "retryable",
                    "page_number",
                    "url",
                )
            )
            connector_reports.append(
                {
                    "key": connector.key,
                    "enabled": connector.enabled,
                    "status": connector.status,
                    "parser_version": connector.parser_version,
                    "summary": (run.summary.get("connectors") or {}).get(connector.key, {}),
                    "sample_records": samples,
                    "errors": errors,
                }
            )

        report = {
            "schema": "pdp-one.setad-live-test.v1",
            "generated_at": timezone.now().isoformat(),
            "run_id": str(run.id),
            "run_status": run.status,
            "page_cap": pages,
            "include_details": False,
            "analyze_after_success": False,
            "source": {
                "key": source.key,
                "enabled": source.enabled,
                "status": source.status,
                "details_policy": source.configuration.get("details_policy"),
            },
            "totals": {
                "pages_processed": run.pages_processed,
                "records_seen": run.records_seen,
                "records_new": run.records_new,
                "records_updated": run.records_updated,
                "records_duplicate": run.records_duplicate,
                "records_failed": run.records_failed,
            },
            "connectors": connector_reports,
            "task_result": result,
        }
        report_text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        self.stdout.write(report_text)

        report_path = options["report"].strip()
        if report_path:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report_text, encoding="utf-8")
            self.stderr.write(self.style.SUCCESS(f"Sanitized report saved to {path}"))

        if run.status in {
            ExtractionRun.Status.FAILED,
            ExtractionRun.Status.PARTIAL,
            ExtractionRun.Status.CANCELLED,
        }:
            raise CommandError(f"SETAD controlled test finished with status: {run.status}")

        self.stderr.write(self.style.SUCCESS("SETAD controlled public-list test completed."))
