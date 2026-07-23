from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0014_disable_parsnamad_tenders"),
    ]

    operations = [
        migrations.AddField(
            model_name="procurementnotice",
            name="importance",
            field=models.CharField(
                choices=[
                    ("low", "کم"),
                    ("medium", "متوسط"),
                    ("high", "زیاد"),
                    ("very_high", "بسیار زیاد"),
                ],
                default="medium",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="directopportunity",
            name="importance",
            field=models.CharField(
                choices=[
                    ("low", "کم"),
                    ("medium", "متوسط"),
                    ("high", "زیاد"),
                    ("very_high", "بسیار زیاد"),
                ],
                default="medium",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="extractionrun",
            name="mode",
            field=models.CharField(
                choices=[
                    ("incremental", "افزایشی"),
                    ("manual_range", "دستی بازه‌دار"),
                ],
                default="incremental",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="extractionrun",
            name="lookback_days",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
