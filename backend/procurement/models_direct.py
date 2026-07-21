from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .models import TimestampedModel


class OpportunityContact(TimestampedModel):
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=200, blank=True)
    organization = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    how_met = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["organization", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "phone"],
                name="proc_opp_contact_identity_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.organization}" if self.organization else self.name


class DirectOpportunity(TimestampedModel):
    class OpportunityType(models.TextChoices):
        UNASSIGNED = "unassigned", "نیازمند تعیین"
        DIRECT_AWARD = "direct_award", "ترک تشریفات"
        DIRECT_NEGOTIATION = "direct_negotiation", "مذاکره مستقیم"
        LIMITED_INVITATION = "limited_invitation", "دعوت محدود"
        EMPLOYER_OUTREACH = "employer_outreach", "رایزنی با کارفرما"
        DIRECT_REFERRAL = "direct_referral", "معرفی مستقیم"
        OFF_SYSTEM_INQUIRY = "off_system_inquiry", "استعلام خارج از سامانه"
        OFF_SYSTEM_TENDER = "off_system_tender", "مناقصه خارج از سامانه"
        BUSINESS_DEVELOPMENT = "business_development", "فرصت توسعه کسب‌وکار"
        OTHER = "other", "سایر"

    class Stage(models.TextChoices):
        NEW = "new", "فرصت جدید"
        REVIEWING = "reviewing", "در حال بررسی"
        FOLLOWING_UP = "following_up", "در حال پیگیری"
        NEGOTIATING = "negotiating", "در حال مذاکره"
        PREPARING = "preparing", "در دست تهیه پیشنهاد"
        SUBMITTED = "submitted", "پیشنهاد ارسال‌شده"
        WON = "won", "موفق"
        LOST = "lost", "ناموفق"
        STOPPED = "stopped", "متوقف‌شده"
        DEFERRED = "deferred", "به تعویق افتاده"
        CONVERTED_TO_NOTICE = "converted_to_notice", "تبدیل‌شده به فراخوان"
        CONVERTED_TO_CONTRACT = "converted_to_contract", "تبدیل‌شده به قرارداد"

    class Probability(models.TextChoices):
        LOW = "low", "پایین"
        MEDIUM = "medium", "متوسط"
        HIGH = "high", "بالا"
        VERY_HIGH = "very_high", "بسیار بالا"

    class Confidentiality(models.TextChoices):
        NORMAL = "normal", "عادی"
        INTERNAL = "internal", "داخلی"
        CONFIDENTIAL = "confidential", "محرمانه"

    title = models.CharField(max_length=600)
    employer_name = models.CharField(max_length=400)
    opportunity_type = models.CharField(
        max_length=32,
        choices=OpportunityType.choices,
        default=OpportunityType.UNASSIGNED,
    )
    stage = models.CharField(max_length=32, choices=Stage.choices, default=Stage.NEW)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_opportunities_responsible",
    )
    next_action = models.CharField(max_length=500)
    next_action_due = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=200, blank=True)
    province = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    estimated_value_rials = models.DecimalField(max_digits=24, decimal_places=0, null=True, blank=True)
    probability = models.CharField(max_length=16, choices=Probability.choices, blank=True)
    probability_percent = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    confidentiality = models.CharField(
        max_length=16,
        choices=Confidentiality.choices,
        default=Confidentiality.INTERNAL,
    )
    source_text = models.CharField(max_length=300, blank=True)
    primary_contact = models.ForeignKey(
        OpportunityContact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_for_opportunities",
    )
    contacts = models.ManyToManyField(OpportunityContact, blank=True, related_name="opportunities")
    last_activity_at = models.DateTimeField(default=timezone.now)
    soft_deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_opportunities_created",
    )

    class Meta:
        ordering = ["next_action_due", "-last_activity_at"]
        indexes = [
            models.Index(fields=["stage", "next_action_due"], name="proc_opp_stage_due_idx"),
            models.Index(fields=["responsible", "stage"], name="proc_opp_owner_stage_idx"),
            models.Index(fields=["employer_name"], name="proc_opp_employer_idx"),
        ]

    def __str__(self):
        return self.title


class OpportunityFollowUp(TimestampedModel):
    class FollowUpType(models.TextChoices):
        PHONE = "phone", "تماس تلفنی"
        MEETING = "meeting", "جلسه"
        EMAIL = "email", "ایمیل"
        MESSAGE = "message", "پیام"
        LETTER = "letter", "نامه"
        VISIT = "visit", "پیگیری حضوری"
        OTHER = "other", "سایر"

    opportunity = models.ForeignKey(DirectOpportunity, on_delete=models.CASCADE, related_name="follow_ups")
    follow_up_type = models.CharField(max_length=16, choices=FollowUpType.choices, default=FollowUpType.PHONE)
    occurred_at = models.DateTimeField(default=timezone.now)
    summary = models.TextField()
    next_action = models.CharField(max_length=500, blank=True)
    next_action_due = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="opportunity_follow_ups_created",
    )

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["opportunity", "occurred_at"], name="proc_opp_follow_time_idx"),
        ]


class OpportunityResult(TimestampedModel):
    class Outcome(models.TextChoices):
        WON = "won", "موفق"
        LOST = "lost", "ناموفق"
        STOPPED = "stopped", "متوقف‌شده"
        DEFERRED = "deferred", "به تعویق افتاده"
        CONVERTED_TO_TENDER = "converted_to_tender", "تبدیل به مناقصه"
        CONVERTED_TO_INQUIRY = "converted_to_inquiry", "تبدیل به استعلام"
        CONVERTED_TO_CONTRACT = "converted_to_contract", "تبدیل به قرارداد"

    opportunity = models.OneToOneField(DirectOpportunity, on_delete=models.PROTECT, related_name="result")
    outcome = models.CharField(max_length=32, choices=Outcome.choices)
    result_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=500)
    notes = models.TextField(blank=True)
    contract = models.ForeignKey(
        "core.Contract",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="originating_opportunities",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="opportunity_results_created",
    )

    class Meta:
        ordering = ["-result_date"]
