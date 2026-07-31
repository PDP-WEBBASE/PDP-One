from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "procurement"
    verbose_name = "فرصت‌ها و مناقصات"

    def ready(self):
        # Keep larger domain model groups in focused modules while still
        # registering them with Django and Celery before checks run.
        from . import (  # noqa: F401
            models_analysis,
            models_automation,
            models_codes,
            models_direct,
            models_documents,
            signals,
            tasks_automation,
            tasks_connector_acceptance,
            tasks_connector_acceptance_v2,
        )
