from django.db import migrations


def configure_setad(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")

    source, _ = ProcurementSource.objects.update_or_create(
        key="setad",
        defaults={
            "name": "ستاد ایران",
            "base_url": "https://setadiran.ir",
            "enabled": True,
            "status": "active",
            "configuration": {
                "public_hosts": ["etend.setadiran.ir", "eproc.setadiran.ir"],
                "source_analysis_completed_at": "2026-07-22",
                "activation_approved_at": "2026-07-23",
                "details_policy": "public-list-only; no captcha bypass",
                "automatic_extraction_requires_global_schedule": True,
            },
        },
    )

    ProcurementConnector.objects.update_or_create(
        key="setad_tenders",
        defaults={
            "source": source,
            "notice_type": "tender",
            "enabled": True,
            "status": "active",
            "list_url_template": (
                "https://etend.setadiran.ir/etend/"
                "callMainPageCartable-anonymous.action?page={page}"
            ),
            "parser_version": "setad-etend-json-v1",
            "supports_detail": False,
            "requires_browser": False,
            "page_size_hint": 30,
            "max_pages": 160,
            "timeout_seconds": 90,
            "retry_count": 2,
            "overlap_days": 2,
        },
    )
    ProcurementConnector.objects.update_or_create(
        key="setad_inquiries",
        defaults={
            "source": source,
            "notice_type": "inquiry",
            "enabled": True,
            "status": "active",
            "list_url_template": "https://eproc.setadiran.ir/eproc/needs.do?page={page}",
            "parser_version": "setad-eproc-needs-html-v1",
            "supports_detail": False,
            "requires_browser": False,
            "page_size_hint": 30,
            "max_pages": 20,
            "timeout_seconds": 90,
            "retry_count": 2,
            "overlap_days": 1,
        },
    )


def restore_pending_setad(apps, schema_editor):
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementSource.objects.filter(key="setad").update(
        base_url="https://fe.setadiran.ir",
        enabled=False,
        status="pending_source_analysis",
        configuration={},
    )
    ProcurementConnector.objects.filter(
        key__in=["setad_tenders", "setad_inquiries"]
    ).update(
        enabled=False,
        status="pending_source_analysis",
        list_url_template="https://fe.setadiran.ir/centralboard/#/central-board-0",
        parser_version="setad-pending-v1",
        supports_detail=True,
        requires_browser=True,
        page_size_hint=None,
    )


class Migration(migrations.Migration):
    dependencies = [("procurement", "0010_procurement_reference_codes")]

    operations = [migrations.RunPython(configure_setad, restore_pending_setad)]
