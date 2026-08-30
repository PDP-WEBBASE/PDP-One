from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent
from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_interaction import (
    ProcurementChangeJournal,
    ProcurementOutboxEvent,
    ProcurementPendingAction,
    ProcurementWriteLease,
)


class ProcurementInteractionContractTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="interaction-user", password="test-pass")
        self.client.force_authenticate(self.user)
        now = timezone.now()
        self.notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="استعلام خدمات مشاوره امروز",
            employer_name="کارفرمای آزمون",
            province="تهران",
            published_date=timezone.localdate(),
            submission_deadline=now + timedelta(hours=3),
            first_seen_at=now,
            last_seen_at=now,
        )
        self.other_notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title="مناقصه آینده",
            employer_name="کارفرمای دوم",
            province="اصفهان",
            published_date=timezone.localdate(),
            submission_deadline=now + timedelta(days=5),
            first_seen_at=now,
            last_seen_at=now,
        )

    def _arm(self, conversation_key="chat-A"):
        response = self.client.post(
            "/api/v1/procurement/interaction/write/arm/",
            {"conversation_key": conversation_key, "ttl_minutes": 60},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["write_armed"])
        return response.data["lease_id"]

    def test_capability_registry_is_readable_without_write_lease(self):
        response = self.client.get("/api/v1/procurement/interaction/capabilities/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema"], "pdp-one.interaction-capabilities.v1")
        self.assertEqual(response.data["safety"]["write_default"], "blocked")
        self.assertTrue(response.data["safety"]["server_side_lease_required"])
        self.assertTrue(response.data["safety"]["ambiguous_write_requires_confirmation"])
        self.assertFalse(response.data["safety"]["generic_database_write"])

    def test_query_is_bounded_and_filters_server_side(self):
        now = timezone.now()
        response = self.client.get(
            "/api/v1/procurement/interaction/query/notices/",
            {
                "notice_type": "inquiry",
                "workflow": "recent",
                "province": "تهران",
                "deadline_from": (now - timedelta(minutes=5)).isoformat(),
                "deadline_to": (now + timedelta(hours=4)).isoformat(),
                "page": 1,
                "page_size": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["page_size"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(str(response.data["results"][0]["id"]), str(self.notice.id))
        self.assertNotIn("count", response.data)

    def test_select_is_fail_closed_without_write_lease(self):
        response = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-A", "lease_id": "", "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProcurementCase.objects.filter(notice=self.notice).exists())

    def test_lease_is_bound_to_conversation_key(self):
        lease_id = self._arm("chat-A")
        response = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-B", "lease_id": lease_id, "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProcurementCase.objects.filter(notice=self.notice).exists())

    def test_expired_lease_is_rejected(self):
        lease_id = self._arm("chat-A")
        ProcurementWriteLease.objects.filter(id=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-A", "lease_id": lease_id, "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProcurementCase.objects.filter(notice=self.notice).exists())

    def test_ambiguous_select_creates_pending_action_without_mutation_then_consumes_confirmation(self):
        lease_id = self._arm("chat-A")
        pending = self.client.post(
            "/api/v1/procurement/interaction/pending/select/",
            {
                "conversation_key": "chat-A",
                "lease_id": lease_id,
                "candidate_notice_ids": [str(self.notice.id), str(self.other_notice.id)],
                "requested_text": "این مورد را منتخب کن",
            },
            format="json",
        )
        self.assertEqual(pending.status_code, 200)
        self.assertTrue(pending.data["confirmation_required"])
        self.assertFalse(pending.data["write_performed"])
        self.assertEqual(ProcurementCase.objects.count(), 0)
        pending_id = pending.data["pending_action_id"]
        self.assertEqual(
            ProcurementPendingAction.objects.get(id=pending_id).status,
            ProcurementPendingAction.Status.AWAITING_CONFIRMATION,
        )

        confirmed = self.client.post(
            "/api/v1/procurement/interaction/pending/select/confirm/",
            {
                "conversation_key": "chat-A",
                "lease_id": lease_id,
                "pending_action_id": pending_id,
                "notice_id": str(self.notice.id),
            },
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(confirmed.data["verified"])
        self.assertTrue(confirmed.data["confirmation_consumed"])
        self.assertEqual(ProcurementCase.objects.filter(notice=self.notice).count(), 1)
        self.assertEqual(ProcurementCase.objects.filter(notice=self.other_notice).count(), 0)
        self.assertEqual(
            ProcurementPendingAction.objects.get(id=pending_id).status,
            ProcurementPendingAction.Status.EXECUTED,
        )

    def test_pending_confirmation_rejects_notice_outside_candidates(self):
        lease_id = self._arm("chat-A")
        third = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.INQUIRY,
            title="گزینه سوم",
            employer_name="کارفرمای سوم",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        pending = self.client.post(
            "/api/v1/procurement/interaction/pending/select/",
            {
                "conversation_key": "chat-A",
                "lease_id": lease_id,
                "candidate_notice_ids": [str(self.notice.id), str(self.other_notice.id)],
            },
            format="json",
        )
        rejected = self.client.post(
            "/api/v1/procurement/interaction/pending/select/confirm/",
            {
                "conversation_key": "chat-A",
                "lease_id": lease_id,
                "pending_action_id": pending.data["pending_action_id"],
                "notice_id": str(third.id),
            },
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(ProcurementCase.objects.count(), 0)

    def test_select_is_verified_audited_versioned_and_idempotent(self):
        lease_id = self._arm("chat-A")
        first = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-A", "lease_id": lease_id, "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data["changed"])
        self.assertTrue(first.data["verified"])
        self.assertEqual(first.data["verification"], "read_after_write")
        self.assertEqual(first.data["current_stage"], ProcurementCase.Stage.SELECTED)
        self.assertEqual(ProcurementCase.objects.filter(notice=self.notice).count(), 1)
        self.assertEqual(ProcurementChangeJournal.objects.count(), 1)
        self.assertEqual(ProcurementOutboxEvent.objects.count(), 1)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="procurement.command.select_notice.v1",
                target_id=str(self.notice.id),
            ).exists()
        )

        changes = self.client.get("/api/v1/procurement/interaction/changes/", {"since": 0})
        self.assertEqual(changes.status_code, 200)
        self.assertEqual(len(changes.data["changes"]), 1)
        self.assertIn("inquiry:selected", changes.data["changes"][0]["affected_contexts"])

        second = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-A", "lease_id": lease_id, "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["changed"])
        self.assertTrue(second.data["idempotent"])
        self.assertTrue(second.data["verified"])
        self.assertEqual(ProcurementCase.objects.filter(notice=self.notice).count(), 1)
        self.assertEqual(ProcurementChangeJournal.objects.count(), 1)
        self.assertEqual(ProcurementOutboxEvent.objects.count(), 1)

    def test_disarm_revokes_write_lease_and_pending_actions(self):
        lease_id = self._arm("chat-A")
        pending = self.client.post(
            "/api/v1/procurement/interaction/pending/select/",
            {
                "conversation_key": "chat-A",
                "lease_id": lease_id,
                "candidate_notice_ids": [str(self.notice.id), str(self.other_notice.id)],
            },
            format="json",
        )
        disarm = self.client.post(
            "/api/v1/procurement/interaction/write/disarm/",
            {"conversation_key": "chat-A"},
            format="json",
        )
        self.assertEqual(disarm.status_code, 200)
        self.assertFalse(disarm.data["write_armed"])
        self.assertEqual(
            ProcurementPendingAction.objects.get(id=pending.data["pending_action_id"]).status,
            ProcurementPendingAction.Status.CANCELLED,
        )
        blocked = self.client.post(
            "/api/v1/procurement/interaction/commands/select-notice/",
            {"conversation_key": "chat-A", "lease_id": lease_id, "notice_id": str(self.notice.id)},
            format="json",
        )
        self.assertEqual(blocked.status_code, 403)
