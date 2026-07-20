from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


class TrialAdminCommandTests(TestCase):
    @patch.dict("os.environ", {
        "PDP_TRIAL_MODE": "true",
        "PDP_TRIAL_ADMIN_USERNAME": "trial-admin",
        "PDP_TRIAL_ADMIN_PASSWORD": "Random-test-password-42!",
    })
    def test_creates_admin_idempotently_and_preserves_existing_password(self):
        call_command("ensure_trial_admin")
        user = get_user_model().objects.get(username="trial-admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("Random-test-password-42!"))

        user.set_password("User-changed-password-88!")
        user.save(update_fields=["password"])
        call_command("ensure_trial_admin")
        user.refresh_from_db()
        self.assertTrue(user.check_password("User-changed-password-88!"))

    @patch.dict("os.environ", {
        "PDP_TRIAL_MODE": "true",
        "PDP_TRIAL_ADMIN_USERNAME": "unsafe-admin",
        "PDP_TRIAL_ADMIN_PASSWORD": "replace-with-a-random-password",
    })
    def test_refuses_placeholder_password(self):
        call_command("ensure_trial_admin")
        self.assertFalse(get_user_model().objects.filter(username="unsafe-admin").exists())

