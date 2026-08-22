from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [("procurement", "0022_disable_automatic_hezareh_detail_enrichment")]

    operations = [
        migrations.CreateModel(
            name="InternetUsageEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activity", models.CharField(choices=[("analysis", "تحلیل با ChatGPT"), ("ci_images", "CI و ساخت Image"), ("deployment", "Deploy"), ("backup", "Backup"), ("web_users", "کاربران وب"), ("unknown", "سایر / نامشخص")], max_length=24)),
                ("source", models.CharField(max_length=64)),
                ("download_bytes", models.PositiveBigIntegerField(default=0)),
                ("upload_bytes", models.PositiveBigIntegerField(default=0)),
                ("operation_count", models.PositiveIntegerField(default=1)),
                ("occurred_at", models.DateTimeField()),
                ("reference", models.CharField(blank=True, max_length=160)),
            ],
            options={"ordering": ["-occurred_at"]},
        ),
        migrations.AddIndex(model_name="internetusageevent", index=models.Index(fields=["activity", "occurred_at"], name="proc_net_activity_time_idx")),
    ]

