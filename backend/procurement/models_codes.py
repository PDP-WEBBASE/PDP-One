from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ProcurementCase, ProcurementNotice
from .models_direct import DirectOpportunity


class ProcurementReferenceSequence(models.Model):
    class Key(models.TextChoices):
        TENDER = "tender", "مناقصه"
        INQUIRY = "inquiry", "استعلام"
        DIRECT = "direct", "ارجاع مستقیم"

    key = models.CharField(max_length=16, choices=Key.choices, unique=True)
    next_value = models.PositiveBigIntegerField(default=10000)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}:{self.next_value}"


class ProcurementReferenceCode(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    kind = models.CharField(max_length=16, choices=ProcurementReferenceSequence.Key.choices)
    notice = models.OneToOneField(
        ProcurementNotice,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reference_record",
    )
    direct_opportunity = models.OneToOneField(
        DirectOpportunity,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reference_record",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(notice__isnull=False, direct_opportunity__isnull=True)
                    | models.Q(notice__isnull=True, direct_opportunity__isnull=False)
                ),
                name="proc_ref_exactly_one_target",
            )
        ]

    def __str__(self):
        return self.code


PREFIX_BY_KEY = {
    ProcurementReferenceSequence.Key.TENDER: "TND",
    ProcurementReferenceSequence.Key.INQUIRY: "INQ",
    ProcurementReferenceSequence.Key.DIRECT: "DIR",
}


@transaction.atomic
def allocate_reference_code(key: str) -> str:
    sequence = ProcurementReferenceSequence.objects.select_for_update().get(key=key)
    value = sequence.next_value
    sequence.next_value = value + 1
    sequence.save(update_fields=["next_value"])
    return f"{PREFIX_BY_KEY[key]}-{value}"


def _has_reference_record(instance) -> bool:
    try:
        instance.reference_record
    except ProcurementReferenceCode.DoesNotExist:
        return False
    return True


@receiver(post_save, sender=ProcurementCase)
def ensure_selected_notice_reference_code(sender, instance, created, **kwargs):
    notice = instance.notice
    if _has_reference_record(notice):
        return
    key = (
        ProcurementReferenceSequence.Key.TENDER
        if notice.resolved_notice_type == ProcurementNotice.NoticeType.TENDER
        else ProcurementReferenceSequence.Key.INQUIRY
    )
    ProcurementReferenceCode.objects.create(
        code=allocate_reference_code(key),
        kind=key,
        notice=notice,
    )


DIRECT_CODE_STAGES = {
    DirectOpportunity.Stage.SELECTED,
    DirectOpportunity.Stage.PREPARING,
    DirectOpportunity.Stage.SUBMITTED,
    DirectOpportunity.Stage.WON,
    DirectOpportunity.Stage.LOST,
    DirectOpportunity.Stage.STOPPED,
    DirectOpportunity.Stage.DEFERRED,
    DirectOpportunity.Stage.CONVERTED_TO_NOTICE,
    DirectOpportunity.Stage.CONVERTED_TO_CONTRACT,
}


@receiver(post_save, sender=DirectOpportunity)
def ensure_selected_direct_reference_code(sender, instance, created, **kwargs):
    if instance.stage not in DIRECT_CODE_STAGES or _has_reference_record(instance):
        return
    key = ProcurementReferenceSequence.Key.DIRECT
    ProcurementReferenceCode.objects.create(
        code=allocate_reference_code(key),
        kind=key,
        direct_opportunity=instance,
    )
