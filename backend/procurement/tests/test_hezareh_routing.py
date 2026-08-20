from django.test import TestCase

from procurement.models import ProcurementConnector
from procurement.tasks import _list_page_url


class HezarehRoutingTests(TestCase):
    def test_tender_first_page_uses_canonical_public_route(self):
        connector = ProcurementConnector.objects.select_related("source").get(key="hezareh_tenders")

        self.assertEqual(
            _list_page_url(connector, 1),
            "https://www.hezarehinfo.net/tenders",
        )
        self.assertEqual(
            _list_page_url(connector, 2),
            "https://www.hezarehinfo.net/tenders/-%21/page-2",
        )

    def test_inquiry_first_page_uses_canonical_public_route(self):
        connector = ProcurementConnector.objects.select_related("source").get(key="hezareh_inquiries")

        self.assertEqual(
            _list_page_url(connector, 1),
            "https://www.hezarehinfo.net/inquiries",
        )
        self.assertEqual(
            _list_page_url(connector, 2),
            "https://www.hezarehinfo.net/inquiries/-%21/page-2",
        )

    def test_explicit_first_page_override_remains_authoritative(self):
        connector = ProcurementConnector.objects.select_related("source").get(key="hezareh_tenders")
        source = connector.source
        configuration = dict(source.configuration or {})
        routes = dict(configuration.get("connector_page_urls") or {})
        tender_route = dict(routes.get("hezareh_tenders") or {})
        tender_route["first_page"] = "https://www.hezarehinfo.net/tenders/custom-first"
        routes["hezareh_tenders"] = tender_route
        configuration["connector_page_urls"] = routes
        source.configuration = configuration
        source.save(update_fields=["configuration", "updated_at"])

        connector.refresh_from_db()
        connector = ProcurementConnector.objects.select_related("source").get(pk=connector.pk)

        self.assertEqual(
            _list_page_url(connector, 1),
            "https://www.hezarehinfo.net/tenders/custom-first",
        )
