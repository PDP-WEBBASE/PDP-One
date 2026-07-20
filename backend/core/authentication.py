import os
import secrets
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

class MCPTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        supplied = header.removeprefix(f"{self.keyword} ").strip()
        expected = os.getenv("PDP_MCP_TOKEN", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            raise AuthenticationFailed("Invalid integration token")
        user, created = get_user_model().objects.get_or_create(
            username="chatgpt-service",
            defaults={"is_active": True},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user, None

