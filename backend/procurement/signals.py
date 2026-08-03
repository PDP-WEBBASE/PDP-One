from django.db.models import BooleanField, Case, F, OuterRef, Subquery, Value, When
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver


@receiver(post_save, sender="procurement.NoticeAnalysisDraft", dispatch_uid="procurement.sync_notice_ai_recommendation_v2")
def sync_notice_ai_recommendation(sender, instance, **kwargs):
    """Keep the notice list flag aligned with the latest AI/human-reviewed draft.

    This only controls visibility in the suggested view. It never approves,
    publishes, selects, or creates a procurement case.
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


@receiver(post_migrate, dispatch_uid="procurement.backfill_notice_ai_recommendation_v2")
def backfill_notice_ai_recommendation_after_migrate(sender, app_config, **kwargs):
    """Backfill all existing notices in one SQL update instead of per-row queries."""
    if app_config.label != "procurement":
        return
    from .models import ProcurementNotice
    from .models_analysis import NoticeAnalysisDraft

    latest_effective_recommendation = (
        NoticeAnalysisDraft.objects.filter(notice_id=OuterRef("pk"))
        .annotate(
            effective_recommendation=Case(
                When(review_status=NoticeAnalysisDraft.ReviewStatus.REJECTED, then=Value(False)),
                default=F("is_recommended"),
                output_field=BooleanField(),
            )
        )
        .order_by("-analyzed_at", "-created_at", "-id")
        .values("effective_recommendation")[:1]
    )
    ProcurementNotice.objects.filter(analysis_drafts__isnull=False).update(
        is_recommended=Subquery(latest_effective_recommendation)
    )


@receiver(post_migrate, dispatch_uid="procurement.bootstrap_guarded_automation_v1")
def bootstrap_guarded_automation_after_migrate(sender, app_config, **kwargs):
    if app_config.label != "procurement":
        return
    from .tasks_automation import bootstrap_guarded_automation

    bootstrap_guarded_automation()
