from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    if text.count(old) != 1:
        raise SystemExit(f"non-unique patch anchor: {label} ({text.count(old)})")
    return text.replace(old, new, 1)


utils_path = ROOT / "backend/procurement/analysis_utils.py"
utils = utils_path.read_text(encoding="utf-8")
utils = replace_once(
    utils,
    '''    source_hashes = sorted(
        notice.source_links.select_related("source_notice")
        .values_list("source_notice__content_hash", flat=True)
    )''',
    '''    prefetched = getattr(notice, "_prefetched_objects_cache", {}).get("source_links")
    if prefetched is not None:
        source_hashes = sorted(
            link.source_notice.content_hash
            for link in prefetched
            if getattr(link, "source_notice", None) is not None
        )
    else:
        source_hashes = sorted(
            notice.source_links.select_related("source_notice")
            .values_list("source_notice__content_hash", flat=True)
        )''',
    "prefetch-aware source hashes",
)
utils_path.write_text(utils, encoding="utf-8")

service_path = ROOT / "backend/procurement/analysis_run_service.py"
service = service_path.read_text(encoding="utf-8")

service = replace_once(
    service,
    '        "sh": "source_hashes",',
    '        "gg": "goods_group",\n        "sg": "service_group",',
    "compact schema groups",
)

basis_pattern = re.compile(
    r"def _compact_basis\(notice: ProcurementNotice\) -> dict\[str, Any\]:\n.*?\n\ndef serialize_claimed_items",
    re.S,
)
basis_replacement = '''def _compact_basis(notice: ProcurementNotice) -> dict[str, Any]:
    source_payloads = [
        link.source_notice.raw_payload or {}
        for link in notice.source_links.all()
        if getattr(link, "source_notice", None) is not None
    ]
    goods_group = next((
        str(payload.get("list", {}).get("goods_group", ""))
        for payload in source_payloads
        if payload.get("list", {}).get("goods_group")
    ), "")
    service_group = next((
        str(payload.get("list", {}).get("service_group", ""))
        for payload in source_payloads
        if payload.get("list", {}).get("service_group")
    ), "")
    mapped = {
        "y": notice.resolved_notice_type,
        "t": notice.title,
        "s": notice.summary,
        "d": notice.description,
        "o": notice.conditions,
        "e": notice.employer_name,
        "no": notice.notice_number,
        "p": notice.province,
        "ct": notice.city,
        "l": notice.execution_location,
        "pd": notice.published_date.isoformat() if notice.published_date else None,
        "dd": notice.submission_deadline.isoformat() if notice.submission_deadline else None,
        "a": str(notice.estimated_amount_rials) if notice.estimated_amount_rials is not None else None,
        "g": str(notice.guarantee_amount_rials) if notice.guarantee_amount_rials is not None else None,
        "q": notice.qualification_text,
        "gg": goods_group,
        "sg": service_group,
    }
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def serialize_claimed_items'''
service, count = basis_pattern.subn(basis_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"compact basis replacement failed: {count}")

service = replace_once(
    service,
    '''    for item in selected:
        item.new_claim_token()
        item.status = ProcurementAnalysisRunItem.Status.CLAIMED
        item.claimed_by = worker_id[:120]
        item.claimed_at = now
        item.claim_expires_at = expires
        item.attempts += 1
        item.save(update_fields=[
            "claim_token", "status", "claimed_by", "claimed_at", "claim_expires_at", "attempts", "updated_at"
        ])''',
    '''    for item in selected:
        item.new_claim_token()
        item.status = ProcurementAnalysisRunItem.Status.CLAIMED
        item.claimed_by = worker_id[:120]
        item.claimed_at = now
        item.claim_expires_at = expires
        item.attempts += 1
        item.updated_at = now
    if selected:
        ProcurementAnalysisRunItem.objects.bulk_update(
            selected,
            ["claim_token", "status", "claimed_by", "claimed_at", "claim_expires_at", "attempts", "updated_at"],
            batch_size=500,
        )''',
    "bulk claim update",
)

loop_pattern = re.compile(
    r"    for index, result in enumerate\(results, start=1\):\n.*?\n    import_record.counts = counts",
    re.S,
)
loop_replacement = '''    normalized_results = [_normalize_result(result) for result in results]
    requested_item_ids = [
        str(result.get("run_item_id") or "")
        for result in normalized_results
        if result.get("run_item_id")
    ]
    item_map = {
        str(item.id): item
        for item in run.items.select_related("notice").prefetch_related(
            "notice__source_links__source_notice",
            "notice__analysis_drafts",
        ).filter(pk__in=requested_item_ids)
    }
    pending_item_updates: dict[str, ProcurementAnalysisRunItem] = {}
    pending_notice_updates: dict[str, ProcurementNotice] = {}

    for index, result in enumerate(normalized_results, start=1):
        try:
            item = item_map.get(str(result.get("run_item_id") or ""))
            if item is None:
                raise ProcurementAnalysisRunItem.DoesNotExist("run_item_not_found")
            if str(result.get("claim_token", "")) != str(item.claim_token or ""):
                counts["rejected"] += 1
                errors.append({"index": str(index), "error": "claim_token_mismatch"})
                continue
            if str(result.get("notice_id", "")) != str(item.notice_id):
                counts["rejected"] += 1
                errors.append({"index": str(index), "error": "notice_id_mismatch"})
                continue
            if str(result.get("notice_content_hash", "")) != item.notice_content_hash:
                counts["invalid_hash"] += 1
                errors.append({"index": str(index), "error": "notice_content_hash_mismatch"})
                continue
            if str(result.get("context_hash", "")) != run.context_snapshot.content_hash:
                counts["invalid_context"] += 1
                errors.append({"index": str(index), "error": "context_hash_mismatch"})
                continue
            current_hash = notice_basis_hash(item.notice)
            if current_hash != item.notice_content_hash:
                counts["invalid_hash"] += 1
                if not dry_run:
                    item.status = ProcurementAnalysisRunItem.Status.RETRY
                    item.last_error = "notice_changed_after_claim"
                    item.claim_token = None
                    item.claim_expires_at = None
                    item.updated_at = timezone.now()
                    pending_item_updates[str(item.id)] = item
                continue

            existing = next((
                draft
                for draft in item.notice.analysis_drafts.all()
                if draft.context_snapshot_id == run.context_snapshot_id
                and draft.notice_content_hash == item.notice_content_hash
            ), None)
            if existing:
                counts["duplicate"] += 1
                if not dry_run:
                    item.draft = existing
                    item.status = ProcurementAnalysisRunItem.Status.COMPLETED
                    item.completed_at = timezone.now()
                    item.claim_token = None
                    item.claim_expires_at = None
                    item.updated_at = timezone.now()
                    pending_item_updates[str(item.id)] = item
                continue
            if dry_run:
                counts["imported"] += 1
                continue

            fields = _draft_payload(result)
            create_draft = _should_create_draft(result)
            raw_output = {
                "engine": "PDP One bulk ChatGPT analysis",
                "format": "pdp-one.compact-result.v1",
                "review_status": "ai_draft",
                "decision_is_draft": True,
                "requires_human_review": True,
                "review_queue": "detailed" if create_draft else "compact",
                "compact_only": not create_draft,
                "run_id": str(run.id),
                "run_item_id": str(item.id),
                "context_hash": run.context_snapshot.content_hash,
                "is_recommended": fields["is_recommended"],
                "score": fields["score"],
                "priority": fields["priority"],
                "category": fields["category"],
                "fit_for_pdp": fields["fit_for_pdp"],
                "reason": fields["reason"],
                "recommended_action": fields["recommended_action"],
                "confidence": fields["confidence"],
                "screening_reason": result.get("screening_reason", ""),
                "urgency": result.get("urgency", ""),
                "analysis_mode": result.get("analysis_mode", "bulk_direct"),
                "matched_qualifications": result.get("matched_qualifications") or [],
                "matched_experience": fields["matched_experience"],
                "risk_notes": fields["risk_notes"],
                "missing_information": result.get("missing_information") or [],
                "result_metadata": result.get("result_metadata") or {},
            }
            if create_draft:
                draft = NoticeAnalysisDraft.objects.create(
                    notice=item.notice,
                    batch=batch,
                    context_snapshot=run.context_snapshot,
                    notice_content_hash=item.notice_content_hash,
                    raw_output=raw_output,
                    model_label=str(result.get("model_label") or "ChatGPT Bulk")[:100],
                    review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
                    created_by_label="ChatGPT",
                    **fields,
                )
                item.draft = draft
                counts["drafts_created"] += 1
            else:
                counts["compact_results"] += 1
            now = timezone.now()
            item.status = ProcurementAnalysisRunItem.Status.COMPLETED
            item.result_metadata = raw_output
            item.completed_at = now
            item.claim_token = None
            item.claim_expires_at = None
            item.last_error = ""
            item.updated_at = now
            pending_item_updates[str(item.id)] = item
            item.notice.processing_status = ProcurementNotice.ProcessingStatus.ANALYZED
            item.notice.updated_at = now
            pending_notice_updates[str(item.notice_id)] = item.notice
            counts["imported"] += 1
        except (ProcurementAnalysisRunItem.DoesNotExist, ValueError, TypeError, IntegrityError) as exc:
            counts["error"] += 1
            errors.append({"index": str(index), "error": str(exc)[:300]})

    if not dry_run and pending_item_updates:
        ProcurementAnalysisRunItem.objects.bulk_update(
            list(pending_item_updates.values()),
            [
                "draft", "status", "result_metadata", "completed_at", "claim_token",
                "claim_expires_at", "last_error", "updated_at",
            ],
            batch_size=500,
        )
    if not dry_run and pending_notice_updates:
        ProcurementNotice.objects.bulk_update(
            list(pending_notice_updates.values()),
            ["processing_status", "updated_at"],
            batch_size=500,
        )

    import_record.counts = counts'''
service, count = loop_pattern.subn(loop_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"import loop replacement failed: {count}")

service_path.write_text(service, encoding="utf-8")

test_path = ROOT / "backend/procurement/tests/test_bulk_chatgpt_analysis.py"
test = test_path.read_text(encoding="utf-8")
test = replace_once(
    test,
    '        self.assertNotIn("d", response.data["items"][0]["b"])\n        self.assertLess(response.data["payload_chars"], 10000)',
    '        self.assertNotIn("d", response.data["items"][0]["b"])\n        self.assertNotIn("sh", response.data["items"][0]["b"])\n        self.assertLess(response.data["payload_chars"], 10000)',
    "compact payload test",
)
test_path.write_text(test, encoding="utf-8")

workflow_path = ROOT / ".github/workflows/apply-bulk-chatgpt-analysis-v1-performance.yml"
script_path = ROOT / "scripts/apply_bulk_chatgpt_analysis_v1_performance.py"
workflow_path.unlink(missing_ok=True)
script_path.unlink(missing_ok=True)
print("bulk ChatGPT analysis v1 performance patch applied")
