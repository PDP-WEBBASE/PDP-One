from django.db import migrations


SETAD_INQUIRY_OLD_MAX_PAGES = 20
SETAD_INQUIRY_NEW_MAX_PAGES = 100
SETAD_INQUIRY_OLD_PARSER = "setad-eproc-needs-html-v1"
SETAD_INQUIRY_NEW_PARSER = "setad-eproc-needs-html-v2-semantic-boundary"


def apply_extraction_health_safeguards(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    ProcurementConnector.objects.filter(key="setad_inquiries").update(
        max_pages=SETAD_INQUIRY_NEW_MAX_PAGES,
        parser_version=SETAD_INQUIRY_NEW_PARSER,
    )


def restore_previous_setad_inquiry_cap(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    ProcurementConnector.objects.filter(key="setad_inquiries").update(
        max_pages=SETAD_INQUIRY_OLD_MAX_PAGES,
        parser_version=SETAD_INQUIRY_OLD_PARSER,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0019_notice_analysis_latest_index"),
    ]

    operations = [
        migrations.RunPython(
            apply_extraction_health_safeguards,
            restore_previous_setad_inquiry_cap,
        )
    ]
