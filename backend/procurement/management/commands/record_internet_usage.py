from django.core.management.base import BaseCommand, CommandError

from procurement.internet_usage import record_internet_usage
from procurement.models_internet_usage import InternetUsageEvent


class Command(BaseCommand):
    help = "Record one completed, metadata-only internet transfer from a trusted host operation."

    def add_arguments(self, parser):
        parser.add_argument("--activity", required=True, choices=[value for value, _ in InternetUsageEvent.Activity.choices])
        parser.add_argument("--source", required=True)
        parser.add_argument("--download-bytes", type=int, default=0)
        parser.add_argument("--upload-bytes", type=int, default=0)
        parser.add_argument("--operation-count", type=int, default=1)
        parser.add_argument("--reference", default="")

    def handle(self, *args, **options):
        if options["download_bytes"] < 0 or options["upload_bytes"] < 0:
            raise CommandError("Byte counters cannot be negative.")
        if options["operation_count"] < 1:
            raise CommandError("Operation count must be at least one.")
        event = record_internet_usage(
            activity=options["activity"],
            source=options["source"],
            download_bytes=options["download_bytes"],
            upload_bytes=options["upload_bytes"],
            operation_count=options["operation_count"],
            reference=options["reference"],
        )
        self.stdout.write(self.style.SUCCESS(str(event.id)))
