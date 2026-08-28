from django.db.models import Q


ACTIVITY_DOMAIN_LABELS = {
    "building": "ساختمان و معماری",
    "urban": "شهرسازی، برنامه‌ریزی و توسعه",
    "mep": "تأسیسات و زیرساخت",
    "renewable": "انرژی‌های تجدیدپذیر",
    "multi": "ترکیبی / بین‌حوزه‌ای",
    "undetermined": "نامشخص / نیازمند تشخیص",
}

ACTIVITY_DOMAIN_KEYWORDS = {
    "renewable": ("تجدیدپذیر", "خورشیدی", "بادی", "solar", "renewable"),
    "urban": ("شهرسازی", "طرح جامع", "برنامه ریزی", "برنامه‌ریزی", "توسعه شهری", "urban"),
    "mep": ("تأسیسات", "تاسیسات", "زیرساخت", "برق", "مکانیک", "آب و فاضلاب", "infrastructure"),
    "building": ("ساختمان", "معماری", "ابنیه", "مسکونی", "building", "architecture"),
    "multi": ("ترکیبی", "بین حوزه", "بین‌حوزه", "چندرشته", "multi"),
}


def classify_activity_domain(value: str | None) -> str:
    token = str(value or "").strip().casefold()
    if not token:
        return "undetermined"
    matches = [
        key for key, keywords in ACTIVITY_DOMAIN_KEYWORDS.items()
        if any(keyword.casefold() in token for keyword in keywords)
    ]
    if len(matches) > 1:
        return "multi"
    return matches[0] if matches else "undetermined"


def activity_domain_query(field_name: str, values: list[str]) -> Q | None:
    requested = list(dict.fromkeys(values))
    if not requested:
        return None
    if any(value not in ACTIVITY_DOMAIN_LABELS for value in requested):
        return Q(pk__in=[])
    query = Q()
    for value in requested:
        if value == "undetermined":
            known = Q()
            for keywords in ACTIVITY_DOMAIN_KEYWORDS.values():
                for keyword in keywords:
                    known |= Q(**{f"{field_name}__icontains": keyword})
            query |= Q(**{f"{field_name}__isnull": True}) | Q(**{field_name: ""}) | ~known
        else:
            value_query = Q()
            for keyword in ACTIVITY_DOMAIN_KEYWORDS[value]:
                value_query |= Q(**{f"{field_name}__icontains": keyword})
            query |= value_query
    return query
