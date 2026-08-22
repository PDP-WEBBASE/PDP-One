from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


UNCLASSIFIED = "unclassified"
CONSULTING = "consulting"
EPC = "epc"
CONSTRUCTION = "construction"

BUSINESS_OPPORTUNITY_TYPE_CHOICES = (
    (UNCLASSIFIED, "نیازمند بررسی"),
    (CONSULTING, "مشاوره"),
    (EPC, "EPC"),
    (CONSTRUCTION, "احداث"),
)
BUSINESS_OPPORTUNITY_TYPE_VALUES = frozenset(value for value, _ in BUSINESS_OPPORTUNITY_TYPE_CHOICES)

UNASSIGNED_SOURCE = "unassigned"
AI_DRAFT_SOURCE = "ai_draft"
AUTOMATED_DRAFT_SOURCE = "automated_draft"
HUMAN_SOURCE = "human"
BUSINESS_OPPORTUNITY_TYPE_SOURCE_CHOICES = (
    (UNASSIGNED_SOURCE, "تعیین نشده"),
    (AI_DRAFT_SOURCE, "پیش‌نویس هوش مصنوعی"),
    (AUTOMATED_DRAFT_SOURCE, "پیش‌نویس خودکار"),
    (HUMAN_SOURCE, "تأیید انسانی"),
)


@dataclass(frozen=True)
class OpportunityTypeClassification:
    value: str = UNCLASSIFIED
    confidence: Decimal | None = None
    reason: str = "اطلاعات کافی برای تعیین نوع فرصت وجود ندارد."
    evidence: tuple[str, ...] = ()


_ALIASES = {
    "consulting": CONSULTING,
    "consultancy": CONSULTING,
    "consultant": CONSULTING,
    "consult": CONSULTING,
    "مشاوره": CONSULTING,
    "خدمات مشاوره": CONSULTING,
    "epc": EPC,
    "engineering procurement construction": EPC,
    "مهندسی تامین و ساخت": EPC,
    "مهندسی تأمین و ساخت": EPC,
    "construction": CONSTRUCTION,
    "construction only": CONSTRUCTION,
    "build": CONSTRUCTION,
    "احداث": CONSTRUCTION,
    "اجرا": CONSTRUCTION,
    "unclassified": UNCLASSIFIED,
    "unknown": UNCLASSIFIED,
    "needs review": UNCLASSIFIED,
    "نیازمند بررسی": UNCLASSIFIED,
    "نامشخص": UNCLASSIFIED,
    "": UNCLASSIFIED,
}


def _normalize_text(value: object) -> str:
    text = str(value or "").casefold()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    text = text.replace("‌", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_business_opportunity_type(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in BUSINESS_OPPORTUNITY_TYPE_VALUES:
        return normalized
    return _ALIASES.get(normalized, UNCLASSIFIED)


def normalize_requested_business_opportunity_types(values: Iterable[object]) -> tuple[list[str], bool]:
    normalized_values: list[str] = []
    invalid = False
    for raw in values:
        token = _normalize_text(raw)
        value = normalize_business_opportunity_type(raw)
        if value == UNCLASSIFIED and token not in {
            "unclassified", "unknown", "needs review", "نیازمند بررسی", "نامشخص"
        }:
            invalid = True
            continue
        if value not in normalized_values:
            normalized_values.append(value)
    return normalized_values, invalid


def normalize_confidence(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return max(Decimal("0"), min(normalized, Decimal("100"))).quantize(Decimal("0.01"))


_EPC_PATTERNS = (
    ("epc", 12),
    ("طرح و ساخت", 10),
    ("طراحی و ساخت", 9),
    ("مهندسی تامین و ساخت", 12),
    ("مهندسی تأمین و ساخت", 12),
    ("طراحی تامین و اجرا", 11),
    ("طراحی تأمین و اجرا", 11),
    ("engineering procurement construction", 12),
)
_CONSULTING_PATTERNS = (
    ("خدمات مشاوره", 8),
    ("مشاور", 5),
    ("مطالعات", 5),
    ("امکان سنجی", 5),
    ("طراحی", 3),
    ("نظارت", 4),
    ("مدیریت طرح", 5),
)
_CONSTRUCTION_PATTERNS = (
    ("احداث", 6),
    ("عملیات اجرایی", 6),
    ("پیمانکاری", 5),
    ("اجرا", 3),
    ("ساخت", 3),
    ("بهسازی", 3),
    ("مرمت", 3),
    ("تعمیر", 2),
)


def _score(text: str, patterns: Iterable[tuple[str, int]]) -> tuple[int, list[str]]:
    total = 0
    evidence = []
    for phrase, weight in patterns:
        if phrase in text:
            total += weight
            evidence.append(phrase)
    return total, evidence


def classify_business_opportunity_type(
    *,
    explicit: object = None,
    explicit_confidence: object = None,
    explicit_reason: object = None,
    evidence_values: Iterable[object] = (),
) -> OpportunityTypeClassification:
    """Return a conservative Draft classification.

    Explicit normalized analysis output wins. Historical/free-text inference requires
    a clear score and margin; ambiguous records remain reviewable and unclassified.
    """

    explicit_text = _normalize_text(explicit)
    explicit_value = normalize_business_opportunity_type(explicit)
    if explicit_text:
        recognized_unclassified = {
            "unclassified", "unknown", "needs review", "نیازمند بررسی", "نامشخص",
        }
        if explicit_value != UNCLASSIFIED:
            reason = str(explicit_reason or "نوع فرصت به‌صورت صریح در خروجی تحلیل ثبت شده است.").strip()
            return OpportunityTypeClassification(
                value=explicit_value,
                confidence=normalize_confidence(explicit_confidence) or Decimal("90.00"),
                reason=reason[:1000],
                evidence=(explicit_text,),
            )
        if explicit_text in recognized_unclassified:
            return OpportunityTypeClassification(
                reason=str(explicit_reason or "خروجی تحلیل، نوع فرصت را نیازمند بررسی انسانی اعلام کرده است.")[:1000],
                evidence=(explicit_text,),
            )
        return OpportunityTypeClassification(
            reason="مقدار صریح نوع فرصت معتبر نیست و برای بررسی انسانی نگه داشته شد.",
            evidence=(explicit_text,),
        )

    text = _normalize_text(" ".join(str(value or "") for value in evidence_values))
    if not text:
        return OpportunityTypeClassification()

    epc_score, epc_evidence = _score(text, _EPC_PATTERNS)
    consulting_score, consulting_evidence = _score(text, _CONSULTING_PATTERNS)
    construction_score, construction_evidence = _score(text, _CONSTRUCTION_PATTERNS)
    ranked = sorted(
        [
            (epc_score, EPC, epc_evidence),
            (consulting_score, CONSULTING, consulting_evidence),
            (construction_score, CONSTRUCTION, construction_evidence),
        ],
        reverse=True,
    )
    best_score, best_value, best_evidence = ranked[0]
    second_score = ranked[1][0]
    minimum = 8 if best_value == EPC else 5
    if best_score < minimum or best_score - second_score < 2:
        return OpportunityTypeClassification(
            reason="شواهد تحلیل برای تعیین قطعی نوع فرصت کافی یا بدون ابهام نیست.",
        )

    confidence = min(88, 58 + best_score * 3 + max(0, best_score - second_score))
    labels = {CONSULTING: "مشاوره", EPC: "EPC", CONSTRUCTION: "احداث"}
    evidence = tuple(dict.fromkeys(best_evidence))[:5]
    return OpportunityTypeClassification(
        value=best_value,
        confidence=Decimal(str(confidence)).quantize(Decimal("0.01")),
        reason=f"پیش‌نویس خودکار نوع «{labels[best_value]}» بر پایه شواهد تحلیل موجود.",
        evidence=evidence,
    )
