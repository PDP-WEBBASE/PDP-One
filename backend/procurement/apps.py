from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "procurement"
    verbose_name = "فرصت‌ها و مناقصات"

    def ready(self):
        # Keep larger domain model groups in focused modules while still
        # registering them with Django before checks and migrations run.
        from . import models_opportunities  # noqa: F401
