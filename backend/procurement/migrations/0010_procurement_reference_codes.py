from django.db import migrations, models
import django.db.models.deletion


PREFIX_BY_KIND = {
    "tender": "TND",
    "inquiry": "INQ",
    "direct": "DIR",
}

DIRECT_CODE_STAGES = [
    "selected",
    "preparing",
    "submitted",
    "won",
    "lost",
    "stopped",
    "deferred",
    "converted_to_notice",
    "converted_to_contract",
]


def seed_reference_codes(apps, schema_editor):
    Sequence = apps.get_model("procurement", "ProcurementReferenceSequence")
    Reference = apps.get_model("procurement", "ProcurementReferenceCode")
    Notice = apps.get_model("procurement", "ProcurementNotice")
    Direct = apps.get_model("procurement", "DirectOpportunity")

    counters = {"tender": 10000, "inquiry": 10000, "direct": 10000}

    selected_notices = Notice.objects.filter(case__isnull=False).order_by("case__created_at", "id")
    for notice in selected_notices.iterator():
        kind = notice.resolved_notice_type
        value = counters[kind]
        Reference.objects.create(
            code=f"{PREFIX_BY_KIND[kind]}-{value}",
            kind=kind,
            notice_id=notice.id,
        )
        counters[kind] = value + 1

    selected_direct = Direct.objects.filter(stage__in=DIRECT_CODE_STAGES).order_by("created_at", "id")
    for opportunity in selected_direct.iterator():
        value = counters["direct"]
        Reference.objects.create(
            code=f"DIR-{value}",
            kind="direct",
            direct_opportunity_id=opportunity.id,
        )
        counters["direct"] = value + 1

    for key, next_value in counters.items():
        Sequence.objects.create(key=key, next_value=next_value)


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0009_procurementsubmissiondocument"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcurementReferenceSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(choices=[("tender", "مناقصه"), ("inquiry", "استعلام"), ("direct", "ارجاع مستقیم")], max_length=16, unique=True)),
                ("next_value", models.PositiveBigIntegerField(default=10000)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="ProcurementReferenceCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=32, unique=True)),
                ("kind", models.CharField(choices=[("tender", "مناقصه"), ("inquiry", "استعلام"), ("direct", "ارجاع مستقیم")], max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("direct_opportunity", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reference_record", to="procurement.directopportunity")),
                ("notice", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reference_record", to="procurement.procurementnotice")),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.AddConstraint(
            model_name="procurementreferencecode",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("direct_opportunity__isnull", True), ("notice__isnull", False))
                    | models.Q(("direct_opportunity__isnull", False), ("notice__isnull", True))
                ),
                name="proc_ref_exactly_one_target",
            ),
        ),
        migrations.RunPython(seed_reference_codes, migrations.RunPython.noop),
    ]
