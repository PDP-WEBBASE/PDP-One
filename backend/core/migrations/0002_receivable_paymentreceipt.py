import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Receivable",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference_code", models.CharField(default=core.models.finance_reference_code, max_length=40, unique=True)),
                ("contract_code", models.CharField(max_length=40)),
                ("contract_title", models.CharField(max_length=300)),
                ("employer", models.CharField(max_length=250)),
                ("statement_title", models.CharField(max_length=200)),
                ("amount_rials", models.DecimalField(decimal_places=0, max_digits=24)),
                ("received_rials", models.DecimalField(decimal_places=0, default=0, max_digits=24)),
                ("due_date", models.DateField()),
                ("status", models.CharField(choices=[("draft", "پیش‌نویس"), ("outstanding", "باز"), ("due_soon", "سررسید نزدیک"), ("overdue", "معوق"), ("pending_approval", "در انتظار تأیید"), ("paid", "وصول شده"), ("cancelled", "لغوشده")], default="draft", max_length=24)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receivables_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["due_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="PaymentReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount_rials", models.DecimalField(decimal_places=0, max_digits=24)),
                ("received_date", models.DateField()),
                ("tracking_code", models.CharField(blank=True, max_length=100)),
                ("note", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "پیش‌نویس"), ("confirmed", "تأییدشده"), ("rejected", "ردشده")], default="draft", max_length=20)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_receipts_created", to=settings.AUTH_USER_MODEL)),
                ("receivable", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="receipts", to="core.receivable")),
            ],
            options={"ordering": ["-received_date", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="receivable",
            index=models.Index(fields=["status", "due_date"], name="core_receiv_status_due_idx"),
        ),
    ]
