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


service_path = ROOT / "backend/procurement/analysis_run_service.py"
service = service_path.read_text(encoding="utf-8")

service = replace_once(
    service,
    '.prefetch_related("source_links__source_notice__connector__source")',
    '.prefetch_related(\n            "source_links__source_notice__connector__source",\n            "analysis_drafts",\n            "persistent_analysis_items",\n        )',
    "candidate prefetch",
)

reason_pattern = re.compile(
    r"def _analysis_reason\(run: ProcurementAnalysisRun, notice: ProcurementNotice, basis_hash: str\) -> str \| None:\n.*?\n\ndef _ensure_legacy_batch",
    re.S,
)
reason_replacement = '''def _analysis_reason(run: ProcurementAnalysisRun, notice: ProcurementNotice, basis_hash: str) -> str | None:
    drafts = list(notice.analysis_drafts.all()) if hasattr(notice, "analysis_drafts") else []
    compact_items = [
        item
        for item in (list(notice.persistent_analysis_items.all()) if hasattr(notice, "persistent_analysis_items") else [])
        if item.status == ProcurementAnalysisRunItem.Status.COMPLETED and bool(item.result_metadata)
    ]
    current_drafts = [draft for draft in drafts if draft.context_snapshot_id == run.context_snapshot_id]
    exact_drafts = [draft for draft in current_drafts if draft.notice_content_hash == basis_hash]
    current_compact = [item for item in compact_items if item.context_hash == run.context_snapshot.content_hash]
    exact_compact = [item for item in current_compact if item.notice_content_hash == basis_hash]

    if run.include_previously_analyzed:
        return "explicit_reanalysis"
    if notice.processing_status == ProcurementNotice.ProcessingStatus.ANALYSIS_FAILED:
        return "previous_analysis_failed"
    if exact_drafts:
        for draft in exact_drafts:
            review = (draft.raw_output or {}).get("human_review") or {}
            if review.get("decision") == "needs_revision":
                return "returned_for_completion"
        return None
    if exact_compact:
        return None
    if not drafts and not compact_items:
        return "never_analyzed"
    if not current_drafts and not current_compact:
        return "analysis_context_changed"
    return "notice_content_changed"


def _ensure_legacy_batch'''
service, count = reason_pattern.subn(reason_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"analysis reason replacement failed: {count}")

service = replace_once(
    service,
    'def claim_run_items(run_id: str, *, worker_id: str, limit: int = 25, lease_seconds: int = 900) -> list[ProcurementAnalysisRunItem]:',
    'def claim_run_items(run_id: str, *, worker_id: str, limit: int = 500, lease_seconds: int = 3600) -> list[ProcurementAnalysisRunItem]:',
    "claim defaults",
)
service = replace_once(
    service,
    '''    queryset = run.items.filter(
        status__in=[ProcurementAnalysisRunItem.Status.PENDING, ProcurementAnalysisRunItem.Status.RETRY]
    ).order_by("sequence")''',
    '''    queryset = run.items.select_related("notice").prefetch_related(
        "notice__source_links__source_notice"
    ).filter(
        status__in=[ProcurementAnalysisRunItem.Status.PENDING, ProcurementAnalysisRunItem.Status.RETRY]
    ).order_by("sequence")''',
    "claim prefetch",
)
service = replace_once(
    service,
    '''    selected = list(queryset[: max(1, min(int(limit), 500))])
    expires = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))''',
    '''    candidates = list(queryset[: max(1, min(int(limit), 500))])
    selected: list[ProcurementAnalysisRunItem] = []
    estimated_payload_chars = 2
    max_payload_chars = 240_000
    for candidate in candidates:
        estimate = len(json.dumps({
            "i": str(candidate.id),
            "n": str(candidate.notice_id),
            "c": candidate.notice_content_hash,
            "ar": candidate.analysis_reason,
            "dp": candidate.deadline_priority,
            "b": _compact_basis(candidate.notice),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) + 48
        if selected and estimated_payload_chars + estimate > max_payload_chars:
            break
        selected.append(candidate)
        estimated_payload_chars += estimate
    expires = now + timedelta(seconds=max(60, min(int(lease_seconds), 3600)))''',
    "adaptive payload budget",
)

basis_pattern = re.compile(
    r"def _compact_basis\(notice: ProcurementNotice\) -> dict\[str, Any\]:\n.*?\n\ndef serialize_claimed_items",
    re.S,
)
basis_replacement = '''def _compact_basis(notice: ProcurementNotice) -> dict[str, Any]:
    source_hashes = sorted(
        link.source_notice.content_hash
        for link in notice.source_links.all()
        if getattr(link, "source_notice", None) is not None
    )
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
        "sh": source_hashes,
    }
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def serialize_claimed_items'''
service, count = basis_pattern.subn(basis_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"compact basis replacement failed: {count}")

should_pattern = re.compile(
    r"def _should_create_draft\(result: dict\[str, Any\]\) -> bool:\n.*?\n\ndef _draft_payload",
    re.S,
)
should_replacement = '''def _should_create_draft(result: dict[str, Any]) -> bool:
    priority = str(result.get("priority") or "").strip().lower()
    screening_reason = str(result.get("screening_reason") or "").strip().lower()
    score = max(0, min(int(result.get("score", 0)), 100))
    material = bool(
        result.get("is_recommended")
        or result.get("missing_information")
        or priority in {"high", "urgent", "critical"}
        or screening_reason in {"ambiguous", "borderline", "needs_information", "needs_review"}
        or score >= 60
    )
    return bool(result.get("create_draft")) or material


def _draft_payload'''
service, count = should_pattern.subn(should_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"draft policy replacement failed: {count}")

service = replace_once(
    service,
    '                "requires_human_review": create_draft,\n                "compact_only": not create_draft,',
    '                "requires_human_review": True,\n                "review_queue": "detailed" if create_draft else "compact",\n                "compact_only": not create_draft,',
    "human review invariant",
)

service = replace_once(
    service,
    '''    valid_notice_ids = set(
        NoticeAnalysisDraft.objects.filter(context_snapshot=context).values_list("notice_id", flat=True)
    )''',
    '''    valid_notice_ids = set(
        NoticeAnalysisDraft.objects.filter(context_snapshot=context).values_list("notice_id", flat=True)
    )
    valid_notice_ids.update(
        ProcurementAnalysisRunItem.objects.filter(
            status=ProcurementAnalysisRunItem.Status.COMPLETED,
            context_hash=context.content_hash,
        ).exclude(result_metadata={}).values_list("notice_id", flat=True)
    )''',
    "queue summary valid ids",
)
service = replace_once(
    service,
    '    for notice in visible.prefetch_related("analysis_drafts").iterator(chunk_size=500):',
    '    for notice in visible.prefetch_related("analysis_drafts", "persistent_analysis_items", "source_links__source_notice").iterator(chunk_size=500):',
    "queue summary prefetch",
)

service_path.write_text(service, encoding="utf-8")

views_path = ROOT / "backend/procurement/views_analysis_runs.py"
views = views_path.read_text(encoding="utf-8")
views = replace_once(
    views,
    '            limit=int(request.data.get("limit") or 25),\n            lease_seconds=int(request.data.get("lease_seconds") or 900),',
    '            limit=int(request.data.get("limit") or 500),\n            lease_seconds=int(request.data.get("lease_seconds") or 3600),',
    "view bulk defaults",
)
views_path.write_text(views, encoding="utf-8")

mcp_path = ROOT / "services/pdp_mcp/procurement_analysis_tools.py"
mcp = mcp_path.read_text(encoding="utf-8")
mcp = replace_once(mcp, '        lease_seconds: int = 900,', '        lease_seconds: int = 3600,', "mcp lease default")
mcp_path.write_text(mcp, encoding="utf-8")

test_path = ROOT / "backend/procurement/tests/test_bulk_chatgpt_analysis.py"
test = test_path.read_text(encoding="utf-8")
test += '''

    def test_compact_result_is_valid_analysis_for_future_runs(self):
        items = claim_run_items(str(self.run.id), worker_id="reuse-test", limit=500, lease_seconds=3600)
        results = []
        for item in items:
            results.append({
                "i": str(item.id),
                "k": str(item.claim_token),
                "n": str(item.notice_id),
                "c": item.notice_content_hash,
                "x": self.context.content_hash,
                "r": False,
                "s": 5,
                "p": "low",
                "f": "نامرتبط",
                "g": "نامرتبط",
                "rs": "تناسب ندارد",
                "a": "عدم پیگیری",
                "cf": 95,
                "cd": False,
            })
        response = self.client.post(self.import_url, {"results": results}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["import"]["counts"]["compact_results"], 2)
        next_run, created = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.assertTrue(created)
        next_run = initialize_run(str(next_run.id), actor=self.user.username)
        self.assertEqual(next_run.items.count(), 0)
'''
test_path.write_text(test, encoding="utf-8")

workflow_path = ROOT / ".github/workflows/apply-bulk-chatgpt-analysis-v1-hardening.yml"
script_path = ROOT / "scripts/apply_bulk_chatgpt_analysis_v1_hardening.py"
workflow_path.unlink(missing_ok=True)
script_path.unlink(missing_ok=True)
print("bulk ChatGPT analysis v1 hardening applied")
