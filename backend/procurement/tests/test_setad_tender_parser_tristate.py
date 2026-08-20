import json

from django.test import SimpleTestCase

from procurement.connectors.setad import SetadEtendParser


class SetadTenderParserTriStateTests(SimpleTestCase):
    def test_false_and_unknown_eligibility_remain_distinct(self):
        payload = {
            "page": 1,
            "total": 1,
            "records": 1,
            "gridModel": [
                {
                    "id": 700101,
                    "number": 2005099999000101,
                    "title": "مناقصه خدمات مشاوره نمونه",
                    "type": "PUBLIC_TENDER",
                    "typeName": "مناقصه عمومی",
                    "organization": {"name": "کارفرمای نمونه"},
                    "operationProvinceName": "تهران",
                    "operationCityName": "تهران",
                    "publicNotificationDate": "1405/05/29 10:00:00",
                    "proposalDeadlineDate": "1405/06/09 12:00:00",
                    "domainsDescription": "خدمات مشاوره",
                    "allowedContractor": False,
                    "allowedConsultation": None,
                    "allowedCommodity": 0,
                    "allowedServices": 1,
                }
            ],
        }
        parser = SetadEtendParser("https://setadiran.ir", "tender")
        page = parser.parse_list(
            json.dumps(payload, ensure_ascii=False),
            "https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=1&rows=30",
        )

        metadata = page.notices[0].metadata
        self.assertIs(metadata["allowed_contractor"], False)
        self.assertIsNone(metadata["allowed_consultation"])
        self.assertIs(metadata["allowed_commodity"], False)
        self.assertIs(metadata["allowed_services"], True)
