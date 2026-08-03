from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver


@receiver(post_save, sender="procurement.NoticeAnalysisDraft", dispatch_uid="procurement.sync_notice_ai_recommendation_v1")
def sync_notice_ai_recommendation(sender, instance, **kwargs):
    """Keep the notice list flag aligned with the latest AI/human-reviewed draft.

    This flag controls the «پیشنهادی» view. Updating it does not approve, publish,
    select, or create a procurement case; the draft remains subject to human review.
    """
    latest = sender.objects.filter(notice_id=instance.notice_id).order_by(
        "-analyzed_at", "-created_at", "-id"
    ).only("is_recommended", "review_status").first()
    if latest is None:
        return
    recommended = bool(latest.is_recommended) and latest.review_status != sender.ReviewStatus.REJECTED
    sender._meta.get_field("notice").remote_field.model.objects.filter(
        pk=instance.notice_id
    ).exclude(is_recommended=recommended).update(is_recommended=recommended)


@receiver(post_migrate, dispatch_uid="procurement.backfill_notice_ai_recommendation_v1")
def backfill_notice_ai_recommendation_after_migrate(sender, app_config, **kwargs):
    """Backfill notices that already have AI drafts created before this fix."""
    if app_config.label != "procurement":
        return
    from .models import ProcurementNotice
    from .models_analysis import NoticeAnalysisDraft

    notice_ids = NoticeAnalysisDraft.objects.order_by().values_list("notice_id", flat=True).distinct()
    for notice_id in notice_ids.iterator(chunk_size=500):
        latest = NoticeAnalysisDraft.objects.filter(notice_id=notice_id).order_by(
            "-analyzed_at", "-created_at", "-id"
        ).only("is_recommended", "review_status").first()
        if latest is None:
            continue
        recommended = bool(latest.is_recommended) and latest.review_status != NoticeAnalysisDraft.ReviewStatus.REJECTED
        ProcurementNotice.objects.filter(pk=notice_id).exclude(
            is_recommended=recommended
        ).update(is_recommended=recommended)


@receiver(post_migrate, dispatch_uid="procurement.bootstrap_guarded_automation_v1")
def bootstrap_guarded_automation_after_migrate(sender, app_config, **kwargs):
    if app_config.label != "procurement":
        return
    from .tasks_automation import bootstrap_guarded_automation

    bootstrap_guarded_automation()
