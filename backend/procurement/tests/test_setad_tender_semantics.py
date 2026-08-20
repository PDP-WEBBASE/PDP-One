from django.test import TestCase

from procurement.connectors.types import ParsedNotice
from procurement.ingestion import ingest_parsed_notice, merge_parsed_notice
from procurement.models import ProcurementConnector
from procurement.models_extraction import ExtractionRun, ExtractionRunItem


class SetadTenderSemanticIngestionTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="setad_tenders")
        self.run = ExtractionRun.objects.create(status=ExtractionRun.Status.RUNNING)
        self.run.connectors.add(self.connector)

    def parsed_notice(
        self,
        *,
        opening_date="1405/05/21 09:00:00",
        allowed_consultation=False,
    ):
        raw_payload = {
            "id": 650152,
            "number": 2005001211000033,
            "title": "فراخوان ارزیابی کیفی شرکت های مشاور انرژی",
            "type": "SHORT_LIST_QUALITY_EVALUATION",
            "typeName": "ارزیابی کیفی برای لیست کوتاه",
            "organization": {"name": "شرکت توزیع برق اصفهان"},
            "operationProvinceName": "اصفهان",
            "operationCityName": "اصفهان",
            "publicNotificationDate": "1405/05/18 19:00:00",
            "documentsDeadlineDate": "1405/05/19 19:00:00",
            "proposalDeadlineDate": "1405/05/20 19:00:00",
            "evaluationDeadlineDate": "1405/05/20 21:00:00",
            "openingDate": opening_date,
            "domainsDescription": "شناسایی و جذب شرکت های مشاور انرژی",
            "allowedContractor": True,
            "allowedConsultation": allowed_consultation,
            "allowedCommodity": False,
            "allowedServices": False,
        }
        return ParsedNotice(
            source_record_id="650152",
            source_url=(
                "https://etend.setadiran.ir/etend/"
                "callMainPageCartable-anonymous.action?page=1&rows=30"
            ),
            detail_url="",
            source_declared_type="tender",
            content_detected_type="tender",
            type_resolution_status="resolved",
            title=raw_payload["title"],
            employer="شرکت توزیع برق اصفهان",
            province="اصفهان",
            published_raw=raw_payload["publicNotificationDate"],
            deadline_raw=raw_payload["proposalDeadlineDate"],
            summary=raw_payload["domainsDescription"],
            description=raw_payload["domainsDescription"],
            notice_number=str(raw_payload["number"]),
            detail_status="access_limited",
            position=1,
            metadata={"setad_channel": "etend", "city": "اصفهان"},
            raw_payload=raw_payload,
        )

    def test_unchanged_tender_lifecycle_is_duplicate_and_preserves_city(self):
        parsed = self.parsed_notice()
        source, notice, status = ingest_parsed_notice(
            self.connector,
            parsed,
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        original_hash = source.content_hash
        self.assertEqual(source.revisions.count(), 1)
        self.assertEqual(notice.city, "اصفهان")
        self.assertIn("_semantic_state", source.raw_payload)

        source, _, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(),
            run=self.run,
            page_number=1,
        )
        source.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.content_hash, original_hash)
        self.assertEqual(source.revisions.count(), 1)

    def test_lifecycle_only_change_creates_semantic_update(self):
        source, _, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(),
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        original_hash = source.content_hash

        source, _, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(opening_date="1405/05/21 11:00:00"),
            run=self.run,
            page_number=1,
        )
        source.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.UPDATED)
        self.assertNotEqual(source.content_hash, original_hash)
        self.assertEqual(source.revisions.count(), 2)

    def test_legacy_tender_bootstraps_semantic_state_without_false_update(self):
        parsed = self.parsed_notice()
        source, _, status = ingest_parsed_notice(
            self.connector,
            parsed,
            run=self.run,
            page_number=1,
        )
        self.assertEqual(status, ExtractionRunItem.Status.NEW)

        legacy_raw = dict(source.raw_payload)
        legacy_raw.pop("_semantic_state", None)
        source.raw_payload = legacy_raw
        source.content_hash = merge_parsed_notice(parsed)["content_hash"]
        source.save(update_fields=["raw_payload", "content_hash", "updated_at"])
        revision_count = source.revisions.count()

        source, _, status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(),
            run=self.run,
            page_number=1,
        )
        source.refresh_from_db()
        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.revisions.count(), revision_count)
        self.assertIn("_semantic_state", source.raw_payload)
