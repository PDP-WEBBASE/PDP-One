import json

from django.test import TestCase
from django.utils import timezone

from procurement.connectors.setad import SetadEtendParser
from procurement.connectors.types import ParsedNotice
from procurement.ingestion import ingest_parsed_notice, merge_parsed_notice
from procurement.models import ProcurementConnector, SourceNotice, SourceNoticeRevision
from procurement.models_extraction import ExtractionRunItem


class SetadTenderSemanticTests(TestCase):
    def setUp(self):
        self.connector = ProcurementConnector.objects.get(key="setad_tenders")

    def parsed_notice(self, *, opening_date="1405/06/10 09:00:00", city="اصفهان"):
        raw = {
            "id": 700001,
            "number": 2005099999000001,
            "title": "مناقصه خدمات مشاوره طراحی نمونه",
            "type": "PUBLIC_TENDER",
            "typeName": "مناقصه عمومی",
            "organization": {"name": "کارفرمای نمونه"},
            "operationProvinceName": "اصفهان",
            "operationCityName": city,
            "publicNotificationDate": "1405/05/29 10:00:00",
            "documentsDeadlineDate": "1405/06/05 12:00:00",
            "proposalDeadlineDate": "1405/06/09 12:00:00",
            "evaluationDeadlineDate": "1405/06/09 13:00:00",
            "openingDate": opening_date,
            "domainsDescription": "خدمات مشاوره طراحی",
            "allowedContractor": False,
            "allowedConsultation": True,
            "allowedCommodity": None,
            "allowedServices": True,
        }
        return ParsedNotice(
            source_record_id="700001",
            source_url="https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=1&rows=30",
            detail_url="",
            source_declared_type="tender",
            content_detected_type="tender",
            type_resolution_status="resolved",
            title=raw["title"],
            employer=raw["organization"]["name"],
            province=raw["operationProvinceName"],
            published_raw=raw["publicNotificationDate"],
            deadline_raw=raw["proposalDeadlineDate"],
            summary=raw["domainsDescription"],
            description=raw["domainsDescription"],
            notice_number=str(raw["number"]),
            detail_status="access_limited",
            metadata={"setad_channel": "etend", "city": city},
            raw_payload=raw,
        )

    def test_new_tender_uses_lifecycle_hash_and_promotes_city(self):
        parsed = self.parsed_notice()
        legacy_core_hash = merge_parsed_notice(parsed)["content_hash"]

        source, notice, status = ingest_parsed_notice(self.connector, parsed)

        self.assertEqual(status, ExtractionRunItem.Status.NEW)
        self.assertNotEqual(source.content_hash, legacy_core_hash)
        self.assertEqual(notice.city, "اصفهان")
        self.assertEqual(source.revisions.count(), 1)
        marker = source.raw_payload["_pdp"]["setad_etend_lifecycle_v1"]
        self.assertEqual(marker["version"], 1)
        self.assertEqual(marker["projection"]["openingDate"], "1405/06/10 09:00:00")
        self.assertIsNone(marker["projection"]["allowedCommodity"])

    def test_lifecycle_only_change_creates_semantic_update_and_revision(self):
        source, _, first_status = ingest_parsed_notice(self.connector, self.parsed_notice())
        first_hash = source.content_hash
        self.assertEqual(first_status, ExtractionRunItem.Status.NEW)

        source, _, second_status = ingest_parsed_notice(
            self.connector,
            self.parsed_notice(opening_date="1405/06/10 10:00:00"),
        )

        self.assertEqual(second_status, ExtractionRunItem.Status.UPDATED)
        self.assertNotEqual(source.content_hash, first_hash)
        self.assertEqual(source.revisions.count(), 2)
        self.assertIn("raw_payload", source.revisions.latest("revision_number").changed_fields)

    def test_legacy_unchanged_row_bootstraps_marker_without_mass_update(self):
        parsed = self.parsed_notice()
        payload = merge_parsed_notice(parsed)
        now = timezone.now()
        source = SourceNotice.objects.create(
            connector=self.connector,
            source_record_id=parsed.source_record_id,
            source_url=parsed.source_url,
            detail_url=parsed.detail_url,
            source_declared_type=parsed.source_declared_type,
            title_raw=parsed.title,
            employer_raw=parsed.employer,
            province_raw=parsed.province,
            published_at_raw=parsed.published_raw,
            deadline_raw=parsed.deadline_raw,
            raw_payload=payload["raw_payload"],
            content_hash=payload["content_hash"],
            detail_status=parsed.detail_status,
            first_seen_at=now,
            last_seen_at=now,
        )
        SourceNoticeRevision.objects.create(
            source_notice=source,
            revision_number=1,
            content_hash=payload["content_hash"],
            raw_payload=payload["raw_payload"],
            parsed_payload=payload,
            changed_fields=["title_raw"],
            parser_version=self.connector.parser_version,
            captured_at=now,
        )
        legacy_hash = source.content_hash

        source, _, status = ingest_parsed_notice(self.connector, parsed)

        self.assertEqual(status, ExtractionRunItem.Status.DUPLICATE)
        self.assertEqual(source.content_hash, legacy_hash)
        self.assertEqual(source.revisions.count(), 1)
        self.assertIn("setad_etend_lifecycle_v1", source.raw_payload["_pdp"])

    def test_etend_parser_preserves_false_vs_unknown_eligibility(self):
        raw = self.parsed_notice().raw_payload
        raw["allowedContractor"] = False
        raw["allowedConsultation"] = None
        payload = {"page": 1, "total": 1, "records": 1, "gridModel": [raw]}
        parser = SetadEtendParser("https://setadiran.ir", "tender")

        page = parser.parse_list(
            json.dumps(payload, ensure_ascii=False),
            "https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=1&rows=30",
        )

        metadata = page.notices[0].metadata
        self.assertIs(metadata["allowed_contractor"], False)
        self.assertIsNone(metadata["allowed_consultation"])
