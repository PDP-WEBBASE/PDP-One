from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent
from procurement.models import ProcurementCase, ProcurementNotice


class CaseFollowUpTests(APITestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(username="follow-manager", password="pass", is_staff=True)
        self.colleague = get_user_model().objects.create_user(username="follow-colleague", password="pass")
        self.viewer = get_user_model().objects.create_user(username="follow-viewer", password="pass")
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="پرونده پیگیری آزمون",
            employer_name="کارفرمای پیگیری",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.case = ProcurementCase.objects.create(
            notice=self.notice,
            stage=ProcurementCase.Stage.EVALUATING,
            created_by=self.manager,
            next_action="بررسی اولیه",
            next_action_due=now - timedelta(hours=1),
        )

    def test_summary_groups_overdue_cases(self):
        response = self.client.get("/api/v1/procurement/cases/follow-up/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["overdue_count"], 1)
        self.assertEqual(response.data["overdue"][0]["notice_title"], self.notice.title)

    def test_staff_can_assign_owner_collaborator_due_and_note(self):
        due = timezone.now() + timedelta(days=2)
        response = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/follow-up/",
            {
                "responsible_username": self.manager.username,
                "collaborator_usernames": [self.colleague.username],
                "next_action": "دریافت اسناد تکمیلی",
                "next_action_due": due.isoformat(),
                "note": "تماس اولیه انجام شد.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["case"]["responsible_username"], self.manager.username)
        self.assertEqual(response.data["collaborator_usernames"], [self.colleague.username])
        self.assertEqual(response.data["notes"][0]["text"], "تماس اولیه انجام شد.")
        self.case.refresh_from_db()
        self.assertEqual(self.case.next_action, "دریافت اسناد تکمیلی")
        self.assertIsNotNone(self.case.next_action_due)
        self.assertTrue(AuditEvent.objects.filter(action="procurement.case.collaborators.set").exists())
        self.assertTrue(AuditEvent.objects.filter(action="procurement.case.follow_up_note").exists())

    def test_invalid_due_is_rejected(self):
        response = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/follow-up/",
            {"collaborator_usernames": [], "next_action_due": "not-a-date"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_staff_cannot_write(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(
            f"/api/v1/procurement/cases/{self.case.id}/follow-up/",
            {"collaborator_usernames": []},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
