from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase


class BrowserSessionRecoveryTests(TestCase):
    endpoint = "/api/v1/auth/session/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="session-recovery-user",
            password="test-password-123",
        )

    def test_normal_session_request_preserves_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(response.json()["username"], self.user.username)
        self.assertNotEqual(response.headers.get("X-PDP-Session-Recovered"), "1")

    def test_recovery_request_bypasses_and_expires_existing_session(self):
        self.client.force_login(self.user)
        self.assertIn(settings.SESSION_COOKIE_NAME, self.client.cookies)

        response = self.client.get(
            f"{self.endpoint}?pdp_reset_session=1",
            HTTP_X_PDP_RESET_SESSION="1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])
        self.assertEqual(response.headers["X-PDP-Session-Recovered"], "1")
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(str(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"]), "0")

        follow_up = self.client.get(self.endpoint)
        self.assertEqual(follow_up.status_code, 200)
        self.assertFalse(follow_up.json()["authenticated"])
