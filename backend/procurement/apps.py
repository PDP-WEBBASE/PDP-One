from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "procurement"
    verbose_name = "فرصت‌ها و مناقصات"

    def ready(self):
        # Keep larger domain model groups in focused modules while still
        # registering them with Django and Celery before checks run. The v2
        # service installs transaction/retry/export hardening before API and
        # task modules import the public service functions. Claim recovery is
        # installed immediately afterwards, then claim-integrity compatibility
        # distinguishes real semantic input changes from ingestion-only hash
        # churn without changing historical Notice hash semantics.
        from . import (  # noqa: F401
            models_analysis,
            models_analysis_runs,
            models_automation,
            models_codes,
            models_direct,
            models_documents,
            models_internet_usage,
            analysis_run_service_v2,
            analysis_claim_recovery,
            analysis_claim_integrity,
            signals,
            tasks_analysis_runs,
            tasks_automation,
            tasks_connector_acceptance,
            tasks_connector_acceptance_v2,
        )
