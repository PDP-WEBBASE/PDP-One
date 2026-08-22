import importlib

from django.db import migrations


def correct_purchase_only_opportunity_types(apps, schema_editor):
    previous = importlib.import_module(
        "procurement.migrations.0024_business_opportunity_types"
    )
    previous.backfill_business_opportunity_types(
        apps,
        schema_editor,
        audit_target="0025",
        current_type="consulting",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0024_business_opportunity_types"),
    ]

    operations = [
        migrations.RunPython(
            correct_purchase_only_opportunity_types,
            migrations.RunPython.noop,
        ),
    ]
