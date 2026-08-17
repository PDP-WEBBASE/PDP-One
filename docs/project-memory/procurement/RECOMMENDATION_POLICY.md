# PDP One — Recommendation Policy

## Canonical effective recommendation

Since PR54, current Tender/Inquiry recommendation must be derived from the **latest effective valid `NoticeAnalysisDraft`**. The compatibility field `ProcurementNotice.is_recommended` is not the canonical source because it may be stale from older analyses/imports.

A rejected latest draft or a latest valid non-recommended analysis removes the Notice from the effective Recommended set.

## History semantics

The Recommended view is intended to preserve the full effective recommendation history rather than only a short recent window. Selection does not erase the record from the historical AI recommendation evidence.

## Human rejection

PR57 `حذف از پیشنهادی` means:

- reject the current effective AI recommendation;
- preserve the Notice;
- preserve analysis history;
- write review/Audit evidence;
- remove it from the effective current Recommended view;
- allow a later genuinely newer analysis to recommend it again.

This is not a permanent blacklist unless a future explicit decision creates such a feature.

## Analysis basis

Recommendation is semantic and multi-criteria. Historical keyword policy explicitly rejects deterministic internal keyword scoring. Keywords/company résumé/qualifications/experience supply Context.

## Human authority

Recommendation is advisory. Selection and participation decisions remain human/company decisions.
