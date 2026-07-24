from django.db import migrations


def configure_shared_safeguards(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    for source in ProcurementSource.objects.all():
        configuration = dict(source.configuration or {})
        configuration.setdefault("content_retry_count", 2)
        configuration.setdefault("content_retry_delay_ms", 1200)
        configuration.setdefault("incomplete_extraction_alerts", True)
        source.configuration = configuration
        source.save(update_fields=["configuration", "updated_at"])

    parsnamad = ProcurementSource.objects.filter(key="parsnamad").first()
    if parsnamad is not None:
        configuration = dict(parsnamad.configuration or {})
        connector_page_urls = dict(configuration.get("connector_page_urls") or {})
        connector_page_urls["parsnamad_tenders"] = {
            "first_page": "https://www.parsnamaddata.com/tender.html",
            "template": "https://www.parsnamaddata.com/tenders/page/{page}",
        }
        configuration["connector_page_urls"] = connector_page_urls
        configuration["tender_type_guard"] = (
            "Reject a page when the dominant detected type conflicts with the tender connector."
        )
        parsnamad.configuration = configuration
        parsnamad.save(update_fields=["configuration", "updated_at"])

    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        list_url_template="https://www.parsnamaddata.com/tenders/page/{page}",
        parser_version="parsnamad-tenders-v3-completeness-guard",
    )


def restore_previous_configuration(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    for source in ProcurementSource.objects.all():
        configuration = dict(source.configuration or {})
        configuration.pop("content_retry_count", None)
        configuration.pop("content_retry_delay_ms", None)
        configuration.pop("incomplete_extraction_alerts", None)
        if source.key == "parsnamad":
            configuration.pop("connector_page_urls", None)
            configuration.pop("tender_type_guard", None)
        source.configuration = configuration
        source.save(update_fields=["configuration", "updated_at"])

    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        list_url_template="https://www.parsnamaddata.com/tender/page-{page}",
        parser_version="parsnamad-tenders-v2",
    )


class Migration(migrations.Migration):
    dependencies = [("procurement", "0012_fix_parsnamad_tender_route")]

    operations = [
        migrations.RunPython(configure_shared_safeguards, restore_previous_configuration)
    ]
