from django.db import migrations


CONFIG_KEY = "hezareh_detail_enrichment_limit"


def disable_automatic_hezareh_detail_enrichment(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    source = ProcurementSource.objects.filter(key="hezareh").first()
    if source is None:
        return

    configuration = dict(source.configuration or {})
    configuration[CONFIG_KEY] = 0
    source.configuration = configuration
    source.save(update_fields=["configuration", "updated_at"])


def restore_automatic_hezareh_detail_default(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    source = ProcurementSource.objects.filter(key="hezareh").first()
    if source is None:
        return

    configuration = dict(source.configuration or {})
    if configuration.get(CONFIG_KEY) == 0:
        configuration.pop(CONFIG_KEY, None)
    source.configuration = configuration
    source.save(update_fields=["configuration", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("procurement", "0021_configure_hezareh_canonical_first_pages")]

    operations = [
        migrations.RunPython(
            disable_automatic_hezareh_detail_enrichment,
            restore_automatic_hezareh_detail_default,
        )
    ]
