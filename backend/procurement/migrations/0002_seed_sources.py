from django.db import migrations


def seed_sources(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    sources = {
        "hezareh": {
            "name": "هزاره",
            "base_url": "https://www.hezarehinfo.net",
            "enabled": True,
            "status": "active",
        },
        "parsnamad": {
            "name": "پارس نماد داده",
            "base_url": "https://www.parsnamaddata.com",
            "enabled": True,
            "status": "active",
        },
        "setad": {
            "name": "ستاد ایران",
            "base_url": "https://fe.setadiran.ir",
            "enabled": False,
            "status": "pending_source_analysis",
        },
    }

    source_records = {}
    for key, defaults in sources.items():
        source, _ = ProcurementSource.objects.update_or_create(key=key, defaults=defaults)
        source_records[key] = source

    connectors = [
        {
            "source": source_records["hezareh"],
            "key": "hezareh_tenders",
            "notice_type": "tender",
            "enabled": True,
            "status": "active",
            "list_url_template": "https://www.hezarehinfo.net/tenders/-%21/page-{page}",
            "parser_version": "hezareh-tenders-v1",
            "page_size_hint": 20,
            "requires_browser": False,
        },
        {
            "source": source_records["hezareh"],
            "key": "hezareh_inquiries",
            "notice_type": "inquiry",
            "enabled": True,
            "status": "active",
            "list_url_template": "https://www.hezarehinfo.net/inquiries/-%21/page-{page}",
            "parser_version": "hezareh-inquiries-v1",
            "page_size_hint": 20,
            "requires_browser": False,
        },
        {
            "source": source_records["parsnamad"],
            "key": "parsnamad_tenders",
            "notice_type": "tender",
            "enabled": True,
            "status": "active",
            "list_url_template": "https://www.parsnamaddata.com/tenders/page/{page}",
            "parser_version": "parsnamad-tenders-v1",
            "page_size_hint": 50,
            "requires_browser": False,
        },
        {
            "source": source_records["parsnamad"],
            "key": "parsnamad_inquiries",
            "notice_type": "inquiry",
            "enabled": True,
            "status": "active",
            "list_url_template": "https://www.parsnamaddata.com/inquiries/page/{page}",
            "parser_version": "parsnamad-inquiries-v1",
            "page_size_hint": 50,
            "requires_browser": False,
        },
        {
            "source": source_records["setad"],
            "key": "setad_tenders",
            "notice_type": "tender",
            "enabled": False,
            "status": "pending_source_analysis",
            "list_url_template": "https://fe.setadiran.ir/centralboard/#/central-board-0",
            "parser_version": "setad-pending-v1",
            "page_size_hint": None,
            "requires_browser": True,
        },
        {
            "source": source_records["setad"],
            "key": "setad_inquiries",
            "notice_type": "inquiry",
            "enabled": False,
            "status": "pending_source_analysis",
            "list_url_template": "https://fe.setadiran.ir/centralboard/#/central-board-0",
            "parser_version": "setad-pending-v1",
            "page_size_hint": None,
            "requires_browser": True,
        },
    ]

    for item in connectors:
        key = item.pop("key")
        ProcurementConnector.objects.update_or_create(key=key, defaults=item)


def unseed_sources(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector.objects.filter(
        key__in=[
            "hezareh_tenders",
            "hezareh_inquiries",
            "parsnamad_tenders",
            "parsnamad_inquiries",
            "setad_tenders",
            "setad_inquiries",
        ]
    ).delete()
    ProcurementSource.objects.filter(key__in=["hezareh", "parsnamad", "setad"]).delete()


class Migration(migrations.Migration):
    dependencies = [("procurement", "0001_initial")]

    operations = [migrations.RunPython(seed_sources, unseed_sources)]
