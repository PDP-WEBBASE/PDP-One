from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from core.models import AuditEvent, PaymentReceipt, Receivable


class FinanceApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="finance-manager", password="Strong-test-password-42")
        self.client.force_authenticate(self.user)

    def create_receivable(self):
        response = self.client.post("/api/v1/receivables/", {
            "contract_code": "PDP-1405-099",
            "contract_title": "مطالعات نمونه",
            "employer": "کارفرمای نمونه",
            "statement_title": "صورت‌وضعیت شماره ۱",
            "amount_rials": "12500000000",
            "received_rials": "0",
            "due_date": "2026-08-15",
            "status": "paid",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_new_receivable_is_always_audited_draft(self):
        response = self.create_receivable()
        self.assertEqual(response.data["status"], Receivable.Status.DRAFT)
        self.assertTrue(AuditEvent.objects.filter(action="receivable.create_draft", target_id=response.data["id"]).exists())

    def test_new_payment_receipt_is_always_audited_draft(self):
        receivable = self.create_receivable()
        response = self.client.post("/api/v1/payment-receipts/", {
            "receivable": receivable.data["id"],
            "amount_rials": "5000000000",
            "received_date": date.today().isoformat(),
            "tracking_code": "BANK-TEST-1",
            "status": "confirmed",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], PaymentReceipt.Status.DRAFT)
        self.assertTrue(AuditEvent.objects.filter(action="payment_receipt.create_draft", target_id=response.data["id"]).exists())

    def test_financial_summary_uses_persisted_records(self):
        self.create_receivable()
        response = self.client.get("/api/v1/financial-summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response.data["open_amount_rials"]), 12500000000)
        self.assertEqual(response.data["open_count"], 1)

    def test_received_amount_cannot_exceed_claim(self):
        response = self.client.post("/api/v1/receivables/", {
            "contract_code": "PDP-1405-100",
            "contract_title": "مطالعات نمونه دوم",
            "employer": "کارفرمای نمونه",
            "statement_title": "صورت‌وضعیت شماره ۲",
            "amount_rials": "100",
            "received_rials": "101",
            "due_date": "2026-08-16",
        }, format="json")
        self.assertEqual(response.status_code, 400)


class SessionApiTests(APITestCase):
    def setUp(self):
        self.password = "Strong-test-password-42"
        self.user = get_user_model().objects.create_user(username="pdp-admin", password=self.password)

    def test_login_requires_csrf_and_creates_session(self):
        client = APIClient(enforce_csrf_checks=True)
        session_response = client.get("/api/v1/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        csrf_token = session_response.data["csrf_token"]
        login_response = client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200, login_response.data)
        self.assertTrue(login_response.data["authenticated"])
