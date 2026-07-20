from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.models import AuditEvent, Contract, Receivable


class TrialSeedTests(TestCase):
    @patch.dict("os.environ", {"PDP_TRIAL_MODE": "true"})
    def test_trial_seed_is_enabled_and_idempotent(self):
        call_command("seed_trial_data")
        call_command("seed_trial_data")
        self.assertEqual(Contract.objects.filter(code="TEST-1405-001").count(), 1)
        self.assertEqual(Receivable.objects.filter(contract_code="TEST-1405-001").count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="contract.create_trial_draft").count(), 1)

    @patch.dict("os.environ", {"PDP_TRIAL_MODE": "false"})
    def test_trial_seed_is_disabled_by_default(self):
        call_command("seed_trial_data")
        self.assertFalse(Contract.objects.filter(code="TEST-1405-001").exists())

