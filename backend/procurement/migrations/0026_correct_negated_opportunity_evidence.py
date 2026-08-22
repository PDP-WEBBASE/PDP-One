import importlib

from django.db import migrations


def correct_negated_opportunity_evidence(apps, schema_editor):
    classifier = importlib.import_module(
        "procurement.migrations.0024_business_opportunity_types"
    )
    classifier.backfill_business_opportunity_types(
        apps,
        schema_editor,
        audit_target="0026",
        current_type="consulting",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0025_correct_purchase_only_opportunity_types"),
    ]

    operations = [
        migrations.RunPython(
            correct_negated_opportunity_evidence,
            migrations.RunPython.noop,
        ),
    ]
