from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from procurement.models import ProcurementCase, ProcurementConnector, ProcurementNotice, ProcurementSource
from procurement.models_extraction import ExtractionRun


class ProcurementSourceApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="viewer", password="test-pass-123")
        self.admin = User.objects.create_user(username="system-admin", password="test-pass-123", is_staff=True)
        self.client = APIClient()

    def test_authenticated_user_can_read_sources_but_cannot_change_them(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/procurement/sources/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

        hezareh = ProcurementSource.objects.get(key="hezareh")
        response = self.client.patch(
            f"/api/v1/procurement/sources/{hezareh.id}/",
            {"enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_parsnamad_tender_and_inquiry_controls_are_independent(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/procurement/sources/")
        self.assertEqual(response.status_code, 200)

        source = next(item for item in response.data["results"] if item["key"] == "parsnamad")
        connectors = {item["notice_type"]: item for item in source["connectors"]}
        self.assertFalse(connectors["tender"]["enabled"])
        self.assertEqual(connectors["tender"]["status"], ProcurementConnector.Status.INACTIVE)
        self.assertIn("همان محتوای استعلامات", connectors["tender"]["operational_note"]["reason"])
        self.assertTrue(connectors["inquiry"]["enabled"])
        self.assertEqual(connectors["inquiry"]["status"], ProcurementConnector.Status.ACTIVE)
        self.assertTrue(source["enabled"])

    def test_system_admin_can_disable_site_and_its_connectors(self):
        self.client.force_authenticate(self.admin)
        hezareh = ProcurementSource.objects.get(key="hezareh")
        response = self.client.patch(
            f"/api/v1/procurement/sources/{hezareh.id}/",
            {"enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        hezareh.refresh_from_db()
        self.assertFalse(hezareh.enabled)
        self.assertEqual(hezareh.status, ProcurementSource.Status.INACTIVE)
        self.assertFalse(
            ProcurementConnector.objects.filter(source=hezareh, enabled=True).exists()
        )

    def test_system_admin_can_disable_one_connector_without_disabling_site(self):
        self.client.force_authenticate(self.admin)
        connector = ProcurementConnector.objects.get(key="parsnamad_inquiries")
        response = self.client.patch(
            f"/api/v1/procurement/connectors/{connector.id}/",
            {"enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        connector.refresh_from_db()
        self.assertFalse(connector.enabled)
        self.assertEqual(connector.status, ProcurementConnector.Status.INACTIVE)
        self.assertTrue(connector.source.enabled)
        tender = ProcurementConnector.objects.get(key="parsnamad_tenders")
        self.assertFalse(tender.enabled)

    def test_system_admin_can_reenable_one_connector_without_changing_the_other(self):
        self.client.force_authenticate(self.admin)
        tender = ProcurementConnector.objects.get(key="parsnamad_tenders")
        inquiry = ProcurementConnector.objects.get(key="parsnamad_inquiries")

        response = self.client.patch(
            f"/api/v1/procurement/connectors/{tender.id}/",
            {"enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        tender.refresh_from_db()
        inquiry.refresh_from_db()
        self.assertTrue(tender.enabled)
        self.assertEqual(tender.status, ProcurementConnector.Status.ACTIVE)
        self.assertTrue(inquiry.enabled)
        self.assertEqual(inquiry.status, ProcurementConnector.Status.ACTIVE)


class ProcurementNoticeApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="expert", password="test-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        now = timezone.now()
        self.tender = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه طراحی ساختمان اداری",
            employer_name="کارفرمای نمونه",
            province="تهران",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.inquiry = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="استعلام خدمات مطالعاتی",
            employer_name="کارفرمای دوم",
            province="البرز",
            first_seen_at=now,
            last_seen_at=now,
        )

    def test_tender_and_inquiry_endpoints_are_separate_views_of_same_model(self):
        tenders = self.client.get("/api/v1/procurement/tenders/")
        inquiries = self.client.get("/api/v1/procurement/inquiries/")

        self.assertEqual(tenders.status_code, 200)
        self.assertEqual(inquiries.status_code, 200)
        self.assertEqual(tenders.data["count"], 1)
        self.assertEqual(inquiries.data["count"], 1)
        self.assertEqual(tenders.data["results"][0]["id"], str(self.tender.id))
        self.assertEqual(inquiries.data["results"][0]["id"], str(self.inquiry.id))

    def test_case_creation_protects_notice_from_retention(self):
        response = self.client.post(
            "/api/v1/procurement/cases/",
            {
                "notice": str(self.tender.id),
                "stage": ProcurementCase.Stage.SELECTED,
                "next_action": "بررسی اسناد",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.tender.refresh_from_db()
        self.assertTrue(self.tender.retention_protected)

    def test_negative_decision_requires_reason(self):
        response = self.client.post(
            "/api/v1/procurement/cases/",
            {
                "notice": str(self.inquiry.id),
                "stage": ProcurementCase.Stage.DO_NOT_PARTICIPATE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("decision_reason", response.data)

    def test_dashboard_reports_active_records(self):
        ProcurementCase.objects.create(
            notice=self.tender,
            responsible=self.user,
            next_action="بررسی اسناد",
        )
        response = self.client.get("/api/v1/procurement/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notices"]["total"], 2)
        self.assertEqual(response.data["cases"]["active"], 1)
        self.assertEqual(response.data["sources"]["enabled_connectors"], 5)
        self.assertEqual(response.data["sources"]["attention_connectors"], 5)
        self.assertFalse(response.data["sources"]["all_healthy"])

    def test_dashboard_marks_partial_connector_as_incomplete(self):
        connector = ProcurementConnector.objects.get(key="hezareh_tenders")
        run = ExtractionRun.objects.create(
            status=ExtractionRun.Status.PARTIAL,
            page_cap=5,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            summary={
                "connectors": {
                    connector.key: {
                        "status": "partial",
                        "pages": 3,
                        "seen": 40,
                        "warnings": 1,
                        "requested_page_cap": 5,
                        "last_successful_page": 2,
                        "reported_total_pages": 95,
                        "completeness": "incomplete",
                        "stop_reason": "unexpected_empty_page",
                        "suspicious_pages": [3],
                        "recovered_pages": [],
                    }
                }
            },
        )
        run.connectors.add(connector)

        response = self.client.get("/api/v1/procurement/dashboard/")

        self.assertEqual(response.status_code, 200)
        health = next(
            item
            for item in response.data["sources"]["connector_health"]
            if item["key"] == connector.key
        )
        self.assertEqual(health["health"], "incomplete")
        self.assertTrue(health["requires_attention"])
        self.assertEqual(health["latest_run"]["last_successful_page"], 2)
        self.assertEqual(health["latest_run"]["suspicious_pages"], [3])
