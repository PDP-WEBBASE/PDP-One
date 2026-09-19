from django.db import migrations


TABLE = "procurement_noticeanalysisdraft"


def refresh_analysis_draft_planner_statistics(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            ALTER TABLE {TABLE}
            SET (
                autovacuum_analyze_scale_factor = 0.02,
                autovacuum_analyze_threshold = 500
            )
            """
        )
        cursor.execute(f"ANALYZE {TABLE}")


def restore_default_analysis_policy(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            ALTER TABLE {TABLE}
            RESET (
                autovacuum_analyze_scale_factor,
                autovacuum_analyze_threshold
            )
            """
        )
        cursor.execute(f"ANALYZE {TABLE}")


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0027_procurement_interaction_contract"),
    ]

    operations = [
        migrations.RunPython(
            refresh_analysis_draft_planner_statistics,
            reverse_code=restore_default_analysis_policy,
        ),
    ]
