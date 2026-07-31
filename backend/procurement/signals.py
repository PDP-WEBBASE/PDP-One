from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate, dispatch_uid="procurement.bootstrap_guarded_automation_v1")
def bootstrap_guarded_automation_after_migrate(sender, app_config, **kwargs):
    if app_config.label != "procurement":
        return
    from .tasks_automation import bootstrap_guarded_automation

    bootstrap_guarded_automation()
