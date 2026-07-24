from django.test import TestCase

from procurement.connectors.base import page_number_from_url, pagination_page_numbers
from procurement.models import ProcurementConnector
from procurement.tasks import _list_page_url


class ConnectorPageRoutingTests(TestCase):
    def test_parsnamad_tender_uses_special_first_page_and_template_afterward(self):
        connector = ProcurementConnector.objects.select_related("source").get(
            key="parsnamad_tenders"
        )

        self.assertEqual(
            _list_page_url(connector, 1),
            "https://www.parsnamaddata.com/tender.html",
        )
        self.assertEqual(
            _list_page_url(connector, 2),
            "https://www.parsnamaddata.com/tenders/page/2",
        )
        self.assertEqual(
            _list_page_url(connector, 25),
            "https://www.parsnamaddata.com/tenders/page/25",
        )

    def test_connector_without_override_uses_its_normal_template(self):
        connector = ProcurementConnector.objects.select_related("source").get(
            key="hezareh_tenders"
        )
        self.assertEqual(
            _list_page_url(connector, 3),
            "https://www.hezarehinfo.net/tenders/-%21/page-3",
        )

    def test_generic_page_number_detection_handles_path_and_query_formats(self):
        self.assertEqual(
            page_number_from_url("https://example.test/tenders/page/17"),
            17,
        )
        self.assertEqual(
            page_number_from_url("https://example.test/list?page=22"),
            22,
        )
        self.assertEqual(
            page_number_from_url("https://example.test/needs.do?pager=true&pageNo=8"),
            8,
        )
        self.assertEqual(
            pagination_page_numbers(
                [
                    "https://example.test/page-1",
                    "https://example.test/page-5",
                    "https://example.test/list?page=3",
                ]
            ),
            [1, 3, 5],
        )
