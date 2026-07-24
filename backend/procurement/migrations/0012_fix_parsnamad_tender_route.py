from django.db import migrations


def fix_parsnamad_tender_route(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        list_url_template="https://www.parsnamaddata.com/tender/page-{page}",
        parser_version="parsnamad-tenders-v2",
        enabled=True,
        status="active",
    )


def restore_previous_route(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        list_url_template="https://www.parsnamaddata.com/tenders/page/{page}",
        parser_version="parsnamad-tenders-v1",
    )


class Migration(migrations.Migration):
    dependencies = [("procurement", "0011_configure_setad_public_connectors")]

    operations = [migrations.RunPython(fix_parsnamad_tender_route, restore_previous_route)]
