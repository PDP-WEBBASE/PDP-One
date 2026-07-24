from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0006_procurement_automation_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="directopportunity",
            name="stage",
            field=models.CharField(
                choices=[
                    ("new", "فرصت جدید"),
                    ("reviewing", "در حال بررسی"),
                    ("following_up", "در حال پیگیری"),
                    ("negotiating", "در حال مذاکره"),
                    ("selected", "منتخب"),
                    ("preparing", "در دست تهیه پیشنهاد"),
                    ("submitted", "پیشنهاد ارسال‌شده"),
                    ("won", "موفق"),
                    ("lost", "ناموفق"),
                    ("stopped", "متوقف‌شده"),
                    ("deferred", "به تعویق افتاده"),
                    ("converted_to_notice", "تبدیل‌شده به فراخوان"),
                    ("converted_to_contract", "تبدیل‌شده به قرارداد"),
                ],
                default="new",
                max_length=32,
            ),
        ),
    ]
