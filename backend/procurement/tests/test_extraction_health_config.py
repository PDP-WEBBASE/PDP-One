from django.test import TestCase

from procurement.models import ProcurementConnector


class ExtractionHealthConfigurationTests(TestCase):
    def test_setad_inquiries_uses_expanded_safety_cap(self):
        connector = ProcurementConnector.objects.get(key="setad_inquiries")
        self.assertEqual(connector.max_pages, 100)
        self.assertEqual(
            connector.parser_version,
            "setad-eproc-needs-html-v2-semantic-boundary",
        )

    def test_parsnamad_tenders_remains_intentionally_disabled(self):
        connector = ProcurementConnector.objects.get(key="parsnamad_tenders")
        self.assertFalse(connector.enabled)
        self.assertEqual(connector.status, ProcurementConnector.Status.INACTIVE)
