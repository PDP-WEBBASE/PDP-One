from django.db import migrations


def disable_parsnamad_tenders(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        enabled=False,
        status="inactive",
    )

    source = ProcurementSource.objects.filter(key="parsnamad").first()
    if source is not None:
        configuration = dict(source.configuration or {})
        controls = dict(configuration.get("connector_controls") or {})
        controls["parsnamad_tenders"] = {
            "reason": (
                "مسیر عمومی مناقصات پارس‌نماد در حال حاضر همان محتوای استعلامات را "
                "برمی‌گرداند؛ برای جلوگیری از ثبت داده نادرست غیرفعال شده است."
            ),
            "reviewed_at": "2026-07-23",
            "can_enable_manually": True,
        }
        configuration["connector_controls"] = controls
        source.configuration = configuration
        source.enabled = True
        source.status = "active"
        source.save(
            update_fields=["configuration", "enabled", "status", "updated_at"]
        )


def restore_parsnamad_tenders(apps, schema_editor):
    ProcurementConnector = apps.get_model("procurement", "ProcurementConnector")
    ProcurementSource = apps.get_model("procurement", "ProcurementSource")

    ProcurementConnector.objects.filter(key="parsnamad_tenders").update(
        enabled=True,
        status="active",
    )

    source = ProcurementSource.objects.filter(key="parsnamad").first()
    if source is not None:
        configuration = dict(source.configuration or {})
        controls = dict(configuration.get("connector_controls") or {})
        controls.pop("parsnamad_tenders", None)
        if controls:
            configuration["connector_controls"] = controls
        else:
            configuration.pop("connector_controls", None)
        source.configuration = configuration
        source.save(update_fields=["configuration", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0013_configure_shared_extraction_safeguards"),
    ]

    operations = [
        migrations.RunPython(disable_parsnamad_tenders, restore_parsnamad_tenders),
    ]
