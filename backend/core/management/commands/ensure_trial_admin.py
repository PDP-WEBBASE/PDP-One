import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the local trial administrator idempotently from environment settings."

    def handle(self, *args, **options):
        if os.getenv("PDP_TRIAL_MODE", "false").lower() not in {"1", "true", "yes"}:
            self.stdout.write("Trial administrator is disabled.")
            return

        username = os.getenv("PDP_TRIAL_ADMIN_USERNAME", "pdp-admin").strip()
        password = os.getenv("PDP_TRIAL_ADMIN_PASSWORD", "")
        if not username or len(password) < 16 or password.startswith("replace-with-"):
            self.stdout.write(self.style.WARNING("Trial administrator was not created because secure local credentials are not configured."))
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username, defaults={"is_staff": True, "is_superuser": True})
        if created:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["password", "is_staff", "is_superuser"])
            self.stdout.write(self.style.SUCCESS("Local trial administrator created."))
        else:
            self.stdout.write("Existing administrator preserved.")

