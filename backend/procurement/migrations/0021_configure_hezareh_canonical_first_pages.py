from django.db import migrations


HEZAREH_FIRST_PAGES = {
    "hezareh_tenders": "https://www.hezarehinfo.net/tenders",
    "hezareh_inquiries": "https://www.hezarehinfo.net/inquiries",
}


def configure_hezareh_first_pages(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    source = ProcurementSource.objects.filter(key="hezareh").first()
    if source is None:
        return

    configuration = dict(source.configuration or {})
    connector_page_urls = dict(configuration.get("connector_page_urls") or {})

    for connector_key, first_page in HEZAREH_FIRST_PAGES.items():
        route = dict(connector_page_urls.get(connector_key) or {})
        route["first_page"] = first_page
        connector_page_urls[connector_key] = route

    configuration["connector_page_urls"] = connector_page_urls
    source.configuration = configuration
    source.save(update_fields=["configuration", "updated_at"])


def remove_hezareh_first_pages(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    source = ProcurementSource.objects.filter(key="hezareh").first()
    if source is None:
        return

    configuration = dict(source.configuration or {})
    connector_page_urls = dict(configuration.get("connector_page_urls") or {})

    for connector_key, first_page in HEZAREH_FIRST_PAGES.items():
        route = dict(connector_page_urls.get(connector_key) or {})
        if route.get("first_page") == first_page:
            route.pop("first_page", None)
        if route:
            connector_page_urls[connector_key] = route
        else:
            connector_page_urls.pop(connector_key, None)

    if connector_page_urls:
        configuration["connector_page_urls"] = connector_page_urls
    else:
        configuration.pop("connector_page_urls", None)

    source.configuration = configuration
    source.save(update_fields=["configuration", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("procurement", "0020_extraction_health_safeguards")]

    operations = [
        migrations.RunPython(configure_hezareh_first_pages, remove_hezareh_first_pages)
    ]
