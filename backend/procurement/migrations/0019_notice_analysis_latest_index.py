from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0018_procurement_analysis_runs"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="noticeanalysisdraft",
            index=models.Index(
                fields=["notice", "-analyzed_at", "-created_at", "-id"],
                name="proc_ana_notice_latest_idx",
            ),
        ),
    ]
