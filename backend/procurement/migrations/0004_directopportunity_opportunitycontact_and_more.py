import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_receivable_paymentreceipt"),
        ("procurement", "0003_extractionrun_extractionpage_extractionerror_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OpportunityContact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("position", models.CharField(blank=True, max_length=200)),
                ("organization", models.CharField(blank=True, max_length=300)),
                ("phone", models.CharField(blank=True, max_length=80)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("how_met", models.CharField(blank=True, max_length=300)),
                ("notes", models.TextField(blank=True)),
            ],
            options={"ordering": ["organization", "name"]},
        ),
        migrations.CreateModel(
            name="DirectOpportunity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=600)),
                ("employer_name", models.CharField(max_length=400)),
                ("opportunity_type", models.CharField(choices=[("unassigned", "نیازمند تعیین"), ("direct_award", "ترک تشریفات"), ("direct_negotiation", "مذاکره مستقیم"), ("limited_invitation", "دعوت محدود"), ("employer_outreach", "رایزنی با کارفرما"), ("direct_referral", "معرفی مستقیم"), ("off_system_inquiry", "استعلام خارج از سامانه"), ("off_system_tender", "مناقصه خارج از سامانه"), ("business_development", "فرصت توسعه کسب‌وکار"), ("other", "سایر")], default="unassigned", max_length=32)),
                ("stage", models.CharField(choices=[("new", "فرصت جدید"), ("reviewing", "در حال بررسی"), ("following_up", "در حال پیگیری"), ("negotiating", "در حال مذاکره"), ("preparing", "در دست تهیه پیشنهاد"), ("submitted", "پیشنهاد ارسال‌شده"), ("won", "موفق"), ("lost", "ناموفق"), ("stopped", "متوقف‌شده"), ("deferred", "به تعویق افتاده"), ("converted_to_notice", "تبدیل‌شده به فراخوان"), ("converted_to_contract", "تبدیل‌شده به قرارداد")], default="new", max_length=32)),
                ("next_action", models.CharField(max_length=500)),
                ("next_action_due", models.DateTimeField(blank=True, null=True)),
                ("description", models.TextField(blank=True)),
                ("domain", models.CharField(blank=True, max_length=200)),
                ("province", models.CharField(blank=True, max_length=120)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("estimated_value_rials", models.DecimalField(blank=True, decimal_places=0, max_digits=24, null=True)),
                ("probability", models.CharField(blank=True, choices=[("low", "پایین"), ("medium", "متوسط"), ("high", "بالا"), ("very_high", "بسیار بالا")], max_length=16)),
                ("probability_percent", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("confidentiality", models.CharField(choices=[("normal", "عادی"), ("internal", "داخلی"), ("confidential", "محرمانه")], default="internal", max_length=16)),
                ("source_text", models.CharField(blank=True, max_length=300)),
                ("last_activity_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("soft_deleted_at", models.DateTimeField(blank=True, null=True)),
                ("contacts", models.ManyToManyField(blank=True, related_name="opportunities", to="procurement.opportunitycontact")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="direct_opportunities_created", to=settings.AUTH_USER_MODEL)),
                ("primary_contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="primary_for_opportunities", to="procurement.opportunitycontact")),
                ("responsible", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="direct_opportunities_responsible", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["next_action_due", "-last_activity_at"],
                "indexes": [
                    models.Index(fields=["stage", "next_action_due"], name="proc_opp_stage_due_idx"),
                    models.Index(fields=["responsible", "stage"], name="proc_opp_owner_stage_idx"),
                    models.Index(fields=["employer_name"], name="proc_opp_employer_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpportunityFollowUp",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("follow_up_type", models.CharField(choices=[("phone", "تماس تلفنی"), ("meeting", "جلسه"), ("email", "ایمیل"), ("message", "پیام"), ("letter", "نامه"), ("visit", "پیگیری حضوری"), ("other", "سایر")], default="phone", max_length=16)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("summary", models.TextField()),
                ("next_action", models.CharField(blank=True, max_length=500)),
                ("next_action_due", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="opportunity_follow_ups_created", to=settings.AUTH_USER_MODEL)),
                ("opportunity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="follow_ups", to="procurement.directopportunity")),
            ],
            options={
                "ordering": ["-occurred_at"],
                "indexes": [models.Index(fields=["opportunity", "occurred_at"], name="proc_opp_follow_time_idx")],
            },
        ),
        migrations.CreateModel(
            name="OpportunityResult",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("outcome", models.CharField(choices=[("won", "موفق"), ("lost", "ناموفق"), ("stopped", "متوقف‌شده"), ("deferred", "به تعویق افتاده"), ("converted_to_tender", "تبدیل به مناقصه"), ("converted_to_inquiry", "تبدیل به استعلام"), ("converted_to_contract", "تبدیل به قرارداد")], max_length=32)),
                ("result_date", models.DateField(default=django.utils.timezone.localdate)),
                ("reason", models.CharField(max_length=500)),
                ("notes", models.TextField(blank=True)),
                ("contract", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="originating_opportunities", to="core.contract")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="opportunity_results_created", to=settings.AUTH_USER_MODEL)),
                ("opportunity", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="result", to="procurement.directopportunity")),
            ],
            options={"ordering": ["-result_date"]},
        ),
        migrations.AddConstraint(
            model_name="opportunitycontact",
            constraint=models.UniqueConstraint(fields=("organization", "name", "phone"), name="proc_opp_contact_identity_uniq"),
        ),
    ]
