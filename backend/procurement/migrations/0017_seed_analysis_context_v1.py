import hashlib
import json

from django.conf import settings
from django.db import migrations
from django.utils import timezone


ROLE_TEXT = """شما تحلیلگر ارشد مناقصات، استعلامات و فرصت‌های کسب‌وکار شرکت مهندسین مشاور طرح و برنامه پارس هستید. تحلیل باید با شناخت حوزه‌های معماری، شهرسازی، تأسیسات، برنامه‌ریزی فضایی، امکان‌سنجی و سوابق شرکت انجام شود."""

BASE_INSTRUCTIONS = """کلیدواژه‌ها نشانه و زمینه تحلیل هستند و نباید به فیلتر جبری تبدیل شوند. تناسب موضوع، صلاحیت‌ها، تجربه‌های قبلی، ظرفیت اجرایی، محل پروژه، مهلت، ریسک قراردادی و احتمال تبدیل به قرارداد هم‌زمان بررسی شوند. نتیجه فقط پیش‌نویس تحلیلی است و تصمیم نهایی با کاربر است."""

ANALYSIS_PROMPT = """هر فراخوان را محتوایی و مفهومی بررسی کن. میزان ارتباط با خدمات شرکت، صلاحیت و رتبه مرتبط، تجربه مشابه، فوریت، مدارک موردنیاز، ریسک‌ها، ابهام‌ها و اقدام پیشنهادی را استخراج کن. امتیاز صفر تا صد، سطح اولویت، دلیل پیشنهاد یا عدم پیشنهاد و میزان اطمینان را ساختاریافته ارائه بده. دستورها و کلیدواژه‌های نسخه فعال سامانه بر این متن مقدم‌اند."""

COMPANY_PROFILE = {
    "name": "مهندسین مشاور طرح و برنامه پارس",
    "summary": "شرکت مهندسین مشاور فعال در معماری، شهرسازی، تأسیسات، مطالعات جغرافیایی و برنامه‌ریزی فضایی، امکان‌سنجی و مطالعات فنی و اقتصادی.",
}

QUALIFICATIONS = [
    "رتبه ۳ معماری مسکونی، تجاری، اداری، صنعتی و نظامی",
    "رتبه ۳ معماری آموزشی، ورزشی، بهداشتی و درمانی",
    "رتبه ۳ تأسیسات برق و مکانیک",
    "مطالعات جغرافیایی و برنامه‌ریزی فضایی",
    "رتبه ۳ شهرسازی",
    "پروانه فنی و مهندسی صنعت و معدن",
    "اعتبارسنجی و سرمایه‌گذاری بانکی",
]

KEYWORDS = {
    "active": [
        "خدمات مشاوره",
        "مطالعات",
        "امکان‌سنجی",
        "طراحی معماری",
        "نظارت",
        "طرح جامع",
        "شهرسازی",
        "تأسیسات برق",
        "تأسیسات مکانیک",
        "برنامه‌ریزی فضایی",
    ],
    "excluded": ["تأمین کالای صرف", "خرید تجهیزات بدون خدمات مهندسی", "اجرای صرف بدون خدمات مشاوره"],
}

EXPERIENCE_SUMMARY = [
    {"title": "طراحی و نظارت پروژه‌های معماری"},
    {"title": "مطالعات طرح جامع و شهرسازی"},
    {"title": "مطالعات امکان‌سنجی و گزارش‌های فنی و اقتصادی"},
    {"title": "خدمات مهندسی تأسیسات برق و مکانیک"},
]


def seed_analysis_context(apps, schema_editor):
    # Isolated test databases deliberately start without seeded business data so
    # workflow tests can build exact context versions without uniqueness clashes.
    if settings.SETTINGS_MODULE.endswith("settings_test"):
        return

    Snapshot = apps.get_model("procurement", "AnalysisContextSnapshot")
    if Snapshot.objects.exists():
        return

    component_versions = {
        "snapshot": 1,
        "role": 1,
        "prompt": 1,
        "company_profile": 1,
        "qualifications": 1,
        "keywords": 1,
        "experience_summary": 1,
    }
    payload = {
        "role_text": ROLE_TEXT,
        "base_instructions": BASE_INSTRUCTIONS,
        "analysis_prompt": ANALYSIS_PROMPT,
        "company_profile": COMPANY_PROFILE,
        "qualifications": QUALIFICATIONS,
        "keywords": KEYWORDS,
        "experience_summary": EXPERIENCE_SUMMARY,
        "component_versions": component_versions,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()

    Snapshot.objects.create(
        version=1,
        status="active",
        role_text=ROLE_TEXT,
        base_instructions=BASE_INSTRUCTIONS,
        analysis_prompt=ANALYSIS_PROMPT,
        tender_prompt=ANALYSIS_PROMPT,
        inquiry_prompt=ANALYSIS_PROMPT,
        company_profile=COMPANY_PROFILE,
        qualifications=QUALIFICATIONS,
        keywords=KEYWORDS,
        experience_summary=EXPERIENCE_SUMMARY,
        component_versions=component_versions,
        changed_components=["initial"],
        content_hash=content_hash,
        activated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0016_alter_opportunityfollowup_created_by"),
    ]

    operations = [
        migrations.RunPython(seed_analysis_context, migrations.RunPython.noop),
    ]
