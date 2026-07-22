import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from procurement.models import NoticeSourceLink, ProcurementConnector, SourceNotice
from procurement.models_extraction import ExtractionRun, ExtractionRunItem
from procurement.tasks import run_extraction


class Command(BaseCommand):
    help = (
        "Remove new records imported by the incorrect Pars Namad tender route "
        "from one controlled test run, then retest the corrected connector."
    )

    def add_arguments(self, parser):
        parser.add_argument("--run-id", default="")
        parser.add_argument("--pages", type=int, default=5)
        parser.add_argument("--report", default="")

    def _find_previous_run(self, connector: ProcurementConnector, run_id: str) -> ExtractionRun:
        if run_id:
            try:
                return ExtractionRun.objects.get(pk=run_id)
            except ExtractionRun.DoesNotExist as exc:
                raise CommandError("The previous controlled test run was not found.") from exc

        candidates = (
            ExtractionRun.objects.filter(connectors=connector)
            .prefetch_related("connectors")
            .order_by("-created_at")[:25]
        )
        for candidate in candidates:
            summary = candidate.summary or {}
            requested = summary.get("requested_connector_keys") or []
            if summary.get("controlled_live_test") and "parsnamad_tenders" in requested:
                if not summary.get("parsnamad_tender_cleanup"):
                    return candidate
        raise CommandError(
            "No unrepaired controlled Pars Namad tender test run was found."
        )

    @transaction.atomic
    def _cleanup(self, run: ExtractionRun, connector: ProcurementConnector) -> dict:
        if not run.summary.get("controlled_live_test"):
            raise CommandError("The selected run is not marked as a controlled live test.")

        items = list(
            run.items.filter(
                connector=connector,
                status=ExtractionRunItem.Status.NEW,
                source_notice__isnull=False,
            ).select_related("source_notice")
        )
        source_notices = []
        seen_ids = set()
        for item in items:
            if item.source_notice_id not in seen_ids:
                source_notices.append(item.source_notice)
                seen_ids.add(item.source_notice_id)

        removed_sources = 0
        removed_notices = 0
        removed_links = 0
        skipped = []

        for source_notice in source_notices:
            if source_notice.extraction_items.exclude(run=run).exists():
                skipped.append(
                    {
                        "source_record_id": source_notice.source_record_id,
                        "reason": "used_by_another_run",
                    }
                )
                continue

            link = (
                NoticeSourceLink.objects.filter(source_notice=source_notice)
                .select_related("procurement_notice")
                .first()
            )
            if link is not None:
                notice = link.procurement_notice
                if notice.retention_protected or hasattr(notice, "case"):
                    skipped.append(
                        {
                            "source_record_id": source_notice.source_record_id,
                            "reason": "protected_or_selected_notice",
                        }
                    )
                    continue

                if notice.source_links.count() == 1:
                    notice.delete()
                    removed_notices += 1
                else:
                    link.delete()
                    removed_links += 1

            source_notice.delete()
            removed_sources += 1

        summary = dict(run.summary or {})
        summary["parsnamad_tender_cleanup"] = {
            "performed_at": timezone.now().isoformat(),
            "candidate_source_notices": len(source_notices),
            "removed_source_notices": removed_sources,
            "removed_procurement_notices": removed_notices,
            "removed_links_only": removed_links,
            "skipped": skipped,
        }
        run.summary = summary
        run.save(update_fields=["summary", "updated_at"])
        return summary["parsnamad_tender_cleanup"]

    def handle(self, *args, **options):
        pages = options["pages"]
        if pages < 1 or pages > 10:
            raise CommandError("--pages must be between 1 and 10.")

        connector = ProcurementConnector.objects.select_related("source").get(
            key="parsnamad_tenders"
        )
        previous_run = self._find_previous_run(connector, options["run_id"].strip())

        connector.enabled = True
        connector.status = ProcurementConnector.Status.ACTIVE
        connector.list_url_template = "https://www.parsnamaddata.com/tender/page-{page}"
        connector.parser_version = "parsnamad-tenders-v2"
        connector.save(
            update_fields=[
                "enabled",
                "status",
                "list_url_template",
                "parser_version",
                "updated_at",
            ]
        )

        cleanup = self._cleanup(previous_run, connector)

        retest = ExtractionRun.objects.create(
            trigger=ExtractionRun.Trigger.MANUAL,
            status=ExtractionRun.Status.QUEUED,
            include_details=False,
            analyze_after_success=False,
            page_cap=pages,
            summary={
                "controlled_live_test": True,
                "repair_retest": True,
                "previous_run_id": str(previous_run.id),
                "requested_connector_keys": ["parsnamad_tenders"],
                "requested_pages_per_connector": pages,
            },
        )
        retest.connectors.add(connector)
        result = run_extraction(str(retest.id))
        retest.refresh_from_db()

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
            retest.errors.order_by("created_at").values(
                "category",
                "safe_message",
                "retryable",
                "page_number",
                "url",
            )
        )
        report = {
            "schema": "pdp-one.parsnamad-tender-repair-retest.v1",
            "generated_at": timezone.now().isoformat(),
            "previous_run_id": str(previous_run.id),
            "cleanup": cleanup,
            "retest_run_id": str(retest.id),
            "retest_status": retest.status,
            "page_cap": pages,
            "connector": {
                "key": connector.key,
                "url_template": connector.list_url_template,
                "parser_version": connector.parser_version,
                "summary": (retest.summary.get("connectors") or {}).get(
                    connector.key, {}
                ),
                "sample_records": samples,
                "errors": errors,
            },
            "task_result": result,
        }
        text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        self.stdout.write(text)

        report_path = options["report"].strip()
        if report_path:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self.stderr.write(self.style.SUCCESS(f"Report saved to {path}"))

        if retest.status in {
            ExtractionRun.Status.FAILED,
            ExtractionRun.Status.PARTIAL,
            ExtractionRun.Status.CANCELLED,
        }:
            raise CommandError(
                f"Pars Namad tender retest finished with status: {retest.status}"
            )

        self.stderr.write(
            self.style.SUCCESS("Pars Namad tender cleanup and retest completed.")
        )
