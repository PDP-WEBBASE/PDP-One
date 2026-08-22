import re
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


TYPE_CHOICES = [
    ("unclassified", "نیازمند بررسی"),
    ("consulting", "مشاوره"),
    ("epc", "EPC"),
    ("construction", "احداث"),
]
SOURCE_CHOICES = [
    ("unassigned", "تعیین نشده"),
    ("ai_draft", "پیش‌نویس هوش مصنوعی"),
    ("automated_draft", "پیش‌نویس خودکار"),
    ("human", "تأیید انسانی"),
]


def _text(value):
    value = str(value or "").casefold()
    value = value.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    value = value.replace("‌", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def _explicit(value):
    value = _text(value)
    aliases = {
        "consulting": "consulting", "consultancy": "consulting", "consultant": "consulting",
        "مشاوره": "consulting", "خدمات مشاوره": "consulting",
        "epc": "epc", "engineering procurement construction": "epc",
        "مهندسی تامین و ساخت": "epc", "مهندسی تأمین و ساخت": "epc",
        "construction": "construction", "construction only": "construction",
        "احداث": "construction", "اجرا": "construction",
    }
    return aliases.get(value)


def _score(text, patterns):
    evidence = [phrase for phrase, _ in patterns if phrase in text]
    return sum(weight for phrase, weight in patterns if phrase in text), evidence


def _classify(explicit, values, confidence=None, reason=""):
    explicit_type = _explicit(explicit)
    if explicit_type:
        try:
            confidence_value = Decimal(str(confidence))
        except Exception:
            confidence_value = Decimal("90.00")
        confidence_value = max(Decimal("0"), min(confidence_value, Decimal("100")))
        return explicit_type, confidence_value, str(reason or "نوع فرصت به‌صورت صریح در خروجی تحلیل ثبت شده است.")[:1000]
    explicit_text = _text(explicit)
    if explicit_text:
        if explicit_text in {"unclassified", "unknown", "needs review", "نیازمند بررسی", "نامشخص"}:
            return "unclassified", None, str(
                reason or "خروجی تحلیل، نوع فرصت را نیازمند بررسی انسانی اعلام کرده است."
            )[:1000]
        return "unclassified", None, "مقدار صریح نوع فرصت معتبر نیست و برای بررسی انسانی نگه داشته شد."

    text = _text(" ".join(str(value or "") for value in values))
    epc = _score(text, [
        ("epc", 12), ("طرح و ساخت", 10), ("طراحی و ساخت", 9),
        ("مهندسی تامین و ساخت", 12), ("مهندسی تأمین و ساخت", 12),
        ("طراحی تامین و اجرا", 11), ("طراحی تأمین و اجرا", 11),
    ])
    consulting = _score(text, [
        ("خدمات مشاوره", 8), ("مشاور", 5), ("مطالعات", 5),
        ("امکان سنجی", 5), ("طراحی", 3), ("نظارت", 4), ("مدیریت طرح", 5),
    ])
    construction = _score(text, [
        ("احداث", 6), ("عملیات اجرایی", 6), ("پیمانکاری", 5),
        ("اجرا", 3), ("ساخت", 3), ("بهسازی", 3), ("مرمت", 3), ("تعمیر", 2),
    ])
    ranked = sorted([
        (epc[0], "epc"), (consulting[0], "consulting"), (construction[0], "construction")
    ], reverse=True)
    best_score, best_type = ranked[0]
    second_score = ranked[1][0]
    minimum = 8 if best_type == "epc" else 5
    if best_score < minimum or best_score - second_score < 2:
        return "unclassified", None, "شواهد تحلیل برای تعیین قطعی نوع فرصت کافی یا بدون ابهام نیست."
    confidence_value = Decimal(str(min(88, 58 + best_score * 3 + max(0, best_score - second_score))))
    labels = {"consulting": "مشاوره", "epc": "EPC", "construction": "احداث"}
    return best_type, confidence_value, f"پیش‌نویس خودکار نوع «{labels[best_type]}» بر پایه شواهد تحلیل موجود."


def backfill_business_opportunity_types(apps, schema_editor):
    Notice = apps.get_model("procurement", "ProcurementNotice")
    Draft = apps.get_model("procurement", "NoticeAnalysisDraft")
    Direct = apps.get_model("procurement", "DirectOpportunity")
    AuditEvent = apps.get_model("core", "AuditEvent")

    draft_updates = []
    notice_updates = []
    direct_updates = []
    seen_notices = set()
    counts = {"drafts": 0, "notices": 0, "direct": 0, "unclassified": 0}

    drafts = Draft.objects.select_related("notice").order_by(
        "notice_id", "-analyzed_at", "-created_at", "-id"
    )
    for draft in drafts.iterator(chunk_size=500):
        raw = draft.raw_output or {}
        result_metadata = raw.get("result_metadata") or {}
        opportunity_type, confidence, reason = _classify(
            raw.get("business_opportunity_type") or raw.get("opportunity_type")
            or result_metadata.get("business_opportunity_type"),
            [
                draft.category, draft.fit_for_pdp, draft.reason, draft.recommended_action,
                draft.notice.title, draft.notice.summary, draft.notice.description,
                draft.notice.conditions, draft.notice.qualification_text,
            ],
            raw.get("business_opportunity_type_confidence"),
            raw.get("business_opportunity_type_reason"),
        )
        draft.business_opportunity_type = opportunity_type
        draft.business_opportunity_type_confidence = confidence
        draft.business_opportunity_type_reason = reason
        draft_updates.append(draft)
        counts["drafts"] += 1
        if opportunity_type == "unclassified":
            counts["unclassified"] += 1

        if draft.notice_id not in seen_notices:
            seen_notices.add(draft.notice_id)
            notice = draft.notice
            if notice.business_opportunity_type_source != "human":
                notice.business_opportunity_type = opportunity_type
                notice.business_opportunity_type_source = (
                    "automated_draft" if opportunity_type != "unclassified" else "unassigned"
                )
                notice.business_opportunity_type_confidence = confidence
                notice.business_opportunity_type_reason = reason
                notice_updates.append(notice)
                counts["notices"] += 1

        if len(draft_updates) >= 500:
            Draft.objects.bulk_update(
                draft_updates,
                ["business_opportunity_type", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
                batch_size=500,
            )
            draft_updates = []
        if len(notice_updates) >= 500:
            Notice.objects.bulk_update(
                notice_updates,
                ["business_opportunity_type", "business_opportunity_type_source", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
                batch_size=500,
            )
            notice_updates = []

    if draft_updates:
        Draft.objects.bulk_update(
            draft_updates,
            ["business_opportunity_type", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
            batch_size=500,
        )
    if notice_updates:
        Notice.objects.bulk_update(
            notice_updates,
            ["business_opportunity_type", "business_opportunity_type_source", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
            batch_size=500,
        )

    for direct in Direct.objects.filter(soft_deleted_at__isnull=True).iterator(chunk_size=500):
        if direct.business_opportunity_type_source == "human":
            continue
        opportunity_type, confidence, reason = _classify(
            None,
            [direct.title, direct.description, direct.domain, direct.next_action, direct.source_text],
        )
        direct.business_opportunity_type = opportunity_type
        direct.business_opportunity_type_source = (
            "automated_draft" if opportunity_type != "unclassified" else "unassigned"
        )
        direct.business_opportunity_type_confidence = confidence
        direct.business_opportunity_type_reason = reason
        direct_updates.append(direct)
        counts["direct"] += 1
        if len(direct_updates) >= 500:
            Direct.objects.bulk_update(
                direct_updates,
                ["business_opportunity_type", "business_opportunity_type_source", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
                batch_size=500,
            )
            direct_updates = []
    if direct_updates:
        Direct.objects.bulk_update(
            direct_updates,
            ["business_opportunity_type", "business_opportunity_type_source", "business_opportunity_type_confidence", "business_opportunity_type_reason"],
            batch_size=500,
        )

    AuditEvent.objects.create(
        actor="migration:procurement.0024",
        action="procurement.business_opportunity_type.backfill",
        target_type="procurement_opportunity_type_projection",
        target_id="0024",
        payload={**counts, "human_choices_overwritten": 0, "draft_only": True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("procurement", "0023_internetusageevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="procurementnotice",
            name="business_opportunity_type",
            field=models.CharField(choices=TYPE_CHOICES, db_index=True, default="unclassified", max_length=20),
        ),
        migrations.AddField(
            model_name="procurementnotice",
            name="business_opportunity_type_source",
            field=models.CharField(choices=SOURCE_CHOICES, default="unassigned", max_length=24),
        ),
        migrations.AddField(
            model_name="procurementnotice",
            name="business_opportunity_type_confidence",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="procurementnotice",
            name="business_opportunity_type_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="noticeanalysisdraft",
            name="business_opportunity_type",
            field=models.CharField(choices=TYPE_CHOICES, db_index=True, default="unclassified", max_length=20),
        ),
        migrations.AddField(
            model_name="noticeanalysisdraft",
            name="business_opportunity_type_confidence",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="noticeanalysisdraft",
            name="business_opportunity_type_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="directopportunity",
            name="business_opportunity_type",
            field=models.CharField(choices=TYPE_CHOICES, db_index=True, default="unclassified", max_length=20),
        ),
        migrations.AddField(
            model_name="directopportunity",
            name="business_opportunity_type_source",
            field=models.CharField(choices=SOURCE_CHOICES, default="unassigned", max_length=24),
        ),
        migrations.AddField(
            model_name="directopportunity",
            name="business_opportunity_type_confidence",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="directopportunity",
            name="business_opportunity_type_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(backfill_business_opportunity_types, migrations.RunPython.noop),
    ]
