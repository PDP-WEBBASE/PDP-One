import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from procurement.models import ProcurementConnector, ProcurementSource, SourceNotice
from procurement.models_extraction import ExtractionRun
from procurement.tasks import run_extraction


CONNECTOR_KEYS = [
    "hezareh_tenders",
    "hezareh_inquiries",
    "parsnamad_tenders",
    "parsnamad_inquiries",
]
SOURCE_KEYS = ["hezareh", "parsnamad"]


class Command(BaseCommand):
    help = (
        "Run a controlled public-list test for Hezareh and Pars Namad "
        "tender and inquiry connectors."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages",
            type=int,
            default=5,
            help="Maximum pages per connector. The controlled-test limit is 10.",
        )
        parser.add_argument(
            "--report",
            default="",
            help="Optional path for the sanitized JSON report.",
        )

    def handle(self, *args, **options):
        pages = options["pages"]
        if pages < 1 or pages > 10:
            raise CommandError("--pages must be between 1 and 10 for the controlled test.")

        sources = list(
            ProcurementSource.objects.filter(key__in=SOURCE_KEYS).order_by("key")
        )
        if len(sources) != len(SOURCE_KEYS):
            raise CommandError("Hezareh or Pars Namad source is missing from the database.")

        started_at = timezone.now().isoformat()
        for source in sources:
            configuration = dict(source.configuration or {})
            configuration.update(
                {
                    "last_controlled_test_started_at": started_at,
                    "last_controlled_test_page_cap": pages,
                    "controlled_test_scope": "public-list-only",
                }
            )
            source.enabled = True
            source.status = ProcurementSource.Status.ACTIVE
            source.configuration = configuration
            source.save(
                update_fields=["enabled", "status", "configuration", "updated_at"]
            )

        connectors = list(
            ProcurementConnector.objects.filter(key__in=CONNECTOR_KEYS)
            .select_related("source")
            .order_by("key")
        )
        if len(connectors) != len(CONNECTOR_KEYS):
            raise CommandError(
                "One or more Hezareh/Pars Namad connectors are missing from the database."
            )

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
                "requested_connector_keys": CONNECTOR_KEYS,
                "requested_pages_per_connector": pages,
                "setad_included": False,
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
                )[:10]
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
                    "source": connector.source.key,
                    "notice_type": connector.notice_type,
                    "enabled": connector.enabled,
                    "status": connector.status,
                    "parser_version": connector.parser_version,
                    "requested_pages": pages,
                    "summary": (run.summary.get("connectors") or {}).get(
                        connector.key, {}
                    ),
                    "sample_records": samples,
                    "errors": errors,
                }
            )

        report = {
            "schema": "pdp-one.hezareh-parsnamad-live-test.v1",
            "generated_at": timezone.now().isoformat(),
            "run_id": str(run.id),
            "run_status": run.status,
            "page_cap_per_connector": pages,
            "expected_connector_count": 4,
            "expected_page_attempts": pages * 4,
            "include_details": False,
            "analyze_after_success": False,
            "setad_included": False,
            "sources": [
                {
                    "key": source.key,
                    "enabled": source.enabled,
                    "status": source.status,
                }
                for source in sources
            ],
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
            raise CommandError(
                "Hezareh/Pars Namad controlled test finished with status: "
                f"{run.status}"
            )

        self.stderr.write(
            self.style.SUCCESS(
                "Hezareh and Pars Namad controlled five-page test completed."
            )
        )
