from django.db import models, transaction


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
