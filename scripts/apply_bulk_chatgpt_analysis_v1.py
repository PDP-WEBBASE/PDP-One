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
    "selected = list(queryset[: max(1, min(int(limit), 250))])",
    "selected = list(queryset[: max(1, min(int(limit), 500))])",
    "claim limit",
)

serializer_pattern = re.compile(
    r"def serialize_claimed_items\(items: Iterable\[ProcurementAnalysisRunItem\]\) -> list\[dict\[str, Any\]\]:\n.*?\n\ndef _draft_payload\(result: dict\[str, Any\]\) -> dict\[str, Any\]:",
    re.S,
)
serializer_replacement = '''COMPACT_CLAIM_SCHEMA = {
    "item": {
        "i": "run_item_id",
        "k": "claim_token",
        "n": "notice_id",
        "c": "notice_content_hash",
        "ar": "analysis_reason",
        "dp": "deadline_priority",
        "b": "analysis_basis",
    },
    "basis": {
        "y": "type",
        "t": "title",
        "s": "summary",
        "d": "description",
        "o": "conditions",
        "e": "employer",
        "no": "notice_number",
        "p": "province",
        "ct": "city",
        "l": "execution_location",
        "pd": "published_date",
        "dd": "submission_deadline",
        "a": "estimated_amount_rials",
        "g": "guarantee_amount_rials",
        "q": "qualification_text",
        "sh": "source_hashes",
    },
    "result": {
        "i": "run_item_id",
        "k": "claim_token",
        "n": "notice_id",
        "c": "notice_content_hash",
        "x": "context_hash",
        "r": "is_recommended",
        "s": "score",
        "p": "priority",
        "f": "fit_for_pdp",
        "g": "category",
        "rs": "reason",
        "a": "recommended_action",
        "mq": "matched_qualifications",
        "me": "matched_experience",
        "rn": "risk_notes",
        "mi": "missing_information",
        "cf": "confidence",
        "m": "analysis_mode",
        "sr": "screening_reason",
        "u": "urgency",
        "cd": "create_draft",
        "md": "model_label",
    },
}


def _compact_basis(notice: ProcurementNotice) -> dict[str, Any]:
    basis = notice_basis_payload(notice)
    mapped = {
        "y": basis.get("type"),
        "t": basis.get("title"),
        "s": basis.get("summary"),
        "d": basis.get("description"),
        "o": basis.get("conditions"),
        "e": basis.get("employer"),
        "no": basis.get("notice_number"),
        "p": basis.get("province"),
        "ct": basis.get("city"),
        "l": basis.get("execution_location"),
        "pd": basis.get("published_date"),
        "dd": basis.get("submission_deadline"),
        "a": basis.get("estimated_amount_rials"),
        "g": basis.get("guarantee_amount_rials"),
        "q": basis.get("qualification_text"),
        "sh": basis.get("source_hashes"),
    }
    return {key: value for key, value in mapped.items() if value not in (None, "", [], {})}


def serialize_claimed_items(items: Iterable[ProcurementAnalysisRunItem]) -> dict[str, Any]:
    selected = list(items)
    if not selected:
        return {
            "format": "pdp-one.compact-claim.v1",
            "schema": COMPACT_CLAIM_SCHEMA,
            "context": None,
            "items": [],
            "payload_chars": 2,
        }
    run = selected[0].run
    payload = [
        {
            "i": str(item.id),
            "k": str(item.claim_token),
            "n": str(item.notice_id),
            "c": item.notice_content_hash,
            "ar": item.analysis_reason,
            "dp": item.deadline_priority,
            "b": _compact_basis(item.notice),
        }
        for item in selected
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "format": "pdp-one.compact-claim.v1",
        "schema": COMPACT_CLAIM_SCHEMA,
        "context": {
            "id": str(run.context_snapshot_id),
            "version": run.context_snapshot.version,
            "hash": run.context_snapshot.content_hash,
        },
        "items": payload,
        "payload_chars": len(canonical),
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


_RESULT_KEY_MAP = {
    "i": "run_item_id",
    "k": "claim_token",
    "n": "notice_id",
    "c": "notice_content_hash",
    "x": "context_hash",
    "r": "is_recommended",
    "s": "score",
    "p": "priority",
    "f": "fit_for_pdp",
    "g": "category",
    "rs": "reason",
    "a": "recommended_action",
    "mq": "matched_qualifications",
    "me": "matched_experience",
    "rn": "risk_notes",
    "mi": "missing_information",
    "cf": "confidence",
    "m": "analysis_mode",
    "sr": "screening_reason",
    "u": "urgency",
    "cd": "create_draft",
    "md": "model_label",
    "rm": "result_metadata",
}


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    for short_key, full_key in _RESULT_KEY_MAP.items():
        if full_key not in normalized and short_key in result:
            normalized[full_key] = result[short_key]
    return normalized


def _should_create_draft(result: dict[str, Any]) -> bool:
    if "create_draft" in result:
        return bool(result.get("create_draft"))
    priority = str(result.get("priority") or "").strip().lower()
    screening_reason = str(result.get("screening_reason") or "").strip().lower()
    score = max(0, min(int(result.get("score", 0)), 100))
    return bool(
        result.get("is_recommended")
        or result.get("missing_information")
        or priority in {"high", "urgent", "critical"}
        or screening_reason in {"ambiguous", "borderline", "needs_information", "needs_review"}
        or score >= 60
    )


def _draft_payload(result: dict[str, Any]) -> dict[str, Any]:'''
service, count = serializer_pattern.subn(serializer_replacement, service, count=1)
if count != 1:
    raise SystemExit(f"serializer replacement failed: {count}")

service = replace_once(
    service,
    '''    counts = {
        "total": len(results),
        "imported": 0,
        "duplicate": 0,
        "rejected": 0,
        "invalid_hash": 0,
        "invalid_context": 0,
        "error": 0,
    }''',
    '''    counts = {
        "total": len(results),
        "imported": 0,
        "drafts_created": 0,
        "compact_results": 0,
        "duplicate": 0,
        "rejected": 0,
        "invalid_hash": 0,
        "invalid_context": 0,
        "error": 0,
    }''',
    "import counters",
)
service = replace_once(
    service,
    '''    for index, result in enumerate(results, start=1):
        try:
            item = run.items.select_related("notice").get(pk=result.get("run_item_id"))''',
    '''    for index, result in enumerate(results, start=1):
        try:
            result = _normalize_result(result)
            item = run.items.select_related("notice").get(pk=result.get("run_item_id"))''',
    "normalize compact results",
)

old_import_block = '''            fields = _draft_payload(result)
            raw_output = {
                "engine": "PDP One persistent analysis run",
                "decision_is_draft": True,
                "requires_human_review": True,
                "run_id": str(run.id),
                "run_item_id": str(item.id),
                "claim_token": str(item.claim_token),
                "context_hash": run.context_snapshot.content_hash,
                "screening_reason": result.get("screening_reason", ""),
                "urgency": result.get("urgency", ""),
                "analysis_mode": result.get("analysis_mode", "deep"),
                "matched_qualifications": result.get("matched_qualifications") or [],
                "missing_information": result.get("missing_information") or [],
                "result_metadata": result.get("result_metadata") or {},
            }
            draft = NoticeAnalysisDraft.objects.create(
                notice=item.notice,
                batch=batch,
                context_snapshot=run.context_snapshot,
                notice_content_hash=item.notice_content_hash,
                raw_output=raw_output,
                model_label=str(result.get("model_label") or "ChatGPT")[:100],
                review_status=NoticeAnalysisDraft.ReviewStatus.AI_DRAFT,
                created_by_label="ChatGPT",
                **fields,
            )
            item.draft = draft
            item.status = ProcurementAnalysisRunItem.Status.COMPLETED
            item.result_metadata = raw_output
            item.completed_at = timezone.now()
            item.claim_token = None
            item.claim_expires_at = None
            item.save(update_fields=[
                "draft", "status", "result_metadata", "completed_at", "claim_token", "claim_expires_at", "updated_at"
            ])
            item.notice.processing_status = ProcurementNotice.ProcessingStatus.ANALYZED
            item.notice.save(update_fields=["processing_status", "updated_at"])
            counts["imported"] += 1'''
new_import_block = '''            fields = _draft_payload(result)
            create_draft = _should_create_draft(result)
            raw_output = {
                "engine": "PDP One bulk ChatGPT analysis",
                "format": "pdp-one.compact-result.v1",
                "decision_is_draft": True,
                "requires_human_review": create_draft,
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
            update_fields = [
                "status", "result_metadata", "completed_at", "claim_token", "claim_expires_at", "updated_at"
            ]
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
                update_fields.insert(0, "draft")
                counts["drafts_created"] += 1
            else:
                counts["compact_results"] += 1
            item.status = ProcurementAnalysisRunItem.Status.COMPLETED
            item.result_metadata = raw_output
            item.completed_at = timezone.now()
            item.claim_token = None
            item.claim_expires_at = None
            item.save(update_fields=update_fields)
            item.notice.processing_status = ProcurementNotice.ProcessingStatus.ANALYZED
            item.notice.save(update_fields=["processing_status", "updated_at"])
            counts["imported"] += 1'''
service = replace_once(service, old_import_block, new_import_block, "compact persistence")
service_path.write_text(service, encoding="utf-8")

views_path = ROOT / "backend/procurement/views_analysis_runs.py"
views = views_path.read_text(encoding="utf-8")
views = replace_once(
    views,
    '''    return Response({
        "run_id": str(run_id),
        "count": len(items),
        "items": serialize_claimed_items(items),
        "decision_is_draft": True,
        "requires_human_review": True,
    })''',
    '''    compact_payload = serialize_claimed_items(items)
    return Response({
        "run_id": str(run_id),
        "count": len(items),
        **compact_payload,
        "decision_is_draft": True,
        "requires_human_review": True,
    })''',
    "compact claim response",
)
views_path.write_text(views, encoding="utf-8")

mcp_path = ROOT / "services/pdp_mcp/procurement_analysis_tools.py"
mcp = mcp_path.read_text(encoding="utf-8")
mcp = replace_once(
    mcp,
    'description="Atomically claim the next safe work package for one analysis worker. Every item includes notice, Content Hash, Context Hash and a lease token.",',
    'description="Claim a compact direct-ChatGPT work package. The response carries Context once per batch, omits empty notice fields, supports up to 500 records, and includes a short-key schema for safe import.",',
    "claim description",
)
mcp = replace_once(mcp, '        limit: int = 25,', '        limit: int = 500,', "claim default")
mcp = replace_once(
    mcp,
    '                "limit": max(1, min(int(limit), 250)),',
    '                "limit": max(1, min(int(limit), 500)),',
    "claim clamp",
)
mcp_path.write_text(mcp, encoding="utf-8")

test_path = ROOT / "backend/procurement/tests/test_bulk_chatgpt_analysis.py"
test_path.write_text('''from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from procurement.analysis_run_service import claim_run_items, create_or_resume_run, initialize_run
from procurement.models import ProcurementNotice
from procurement.models_analysis import AnalysisContextSnapshot, NoticeAnalysisDraft
from procurement.models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


class BulkChatGPTAnalysisTests(APITransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="bulk-chatgpt", password="test", is_staff=True)
        self.client.force_authenticate(self.user)
        self.context = AnalysisContextSnapshot.objects.create(
            version=902,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر مستقیم",
            base_instructions="همه رکوردها توسط ChatGPT تحلیل شوند.",
            analysis_prompt="تحلیل حجمی مستقیم انجام بده.",
            company_profile={"name": "PDP"},
            qualifications=["معماری", "تأسیسات"],
            keywords={"active": ["مطالعات", "طراحی"]},
            experience_summary=[{"title": "طراحی و نظارت"}],
            component_versions={"snapshot": 902},
        )
        now = timezone.now()
        for index, title in enumerate([
            "خرید کالای نامرتبط",
            "انتخاب مشاور طراحی و نظارت ساختمان اداری",
        ]):
            ProcurementNotice.objects.create(
                resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
                title=title,
                summary="" if index == 0 else "خدمات مهندسی مشاور",
                description="",
                employer_name="کارفرما",
                province="تهران",
                processing_status=ProcurementNotice.ProcessingStatus.READY_FOR_ANALYSIS,
                first_seen_at=now,
                last_seen_at=now,
            )
        run, _ = create_or_resume_run(
            run_type=ProcurementAnalysisRun.RunType.INCREMENTAL,
            trigger=ProcurementAnalysisRun.Trigger.MANUAL_CHATGPT,
            scope=ProcurementAnalysisRun.Scope.ALL_PENDING,
            actor=self.user.username,
            requested_by=self.user,
        )
        self.run = initialize_run(str(run.id), actor=self.user.username)
        self.claim_url = f"/api/v1/procurement/analysis/runs/{self.run.id}/claim/"
        self.import_url = f"/api/v1/procurement/analysis/runs/{self.run.id}/results/import/"

    def test_claim_is_compact_context_is_batch_level_and_empty_fields_are_omitted(self):
        response = self.client.post(self.claim_url, {"limit": 500, "lease_seconds": 3600}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["format"], "pdp-one.compact-claim.v1")
        self.assertEqual(response.data["context"]["hash"], self.context.content_hash)
        self.assertEqual(response.data["count"], 2)
        self.assertNotIn("context_hash", response.data["items"][0])
        self.assertNotIn("d", response.data["items"][0]["b"])
        self.assertLess(response.data["payload_chars"], 10000)

    def test_compact_results_store_all_outcomes_but_create_draft_only_for_material_items(self):
        items = claim_run_items(str(self.run.id), worker_id="bulk-test", limit=500, lease_seconds=3600)
        compact_results = []
        for index, item in enumerate(items):
            compact_results.append({
                "i": str(item.id),
                "k": str(item.claim_token),
                "n": str(item.notice_id),
                "c": item.notice_content_hash,
                "x": self.context.content_hash,
                "r": index == 1,
                "s": 10 if index == 0 else 90,
                "p": "low" if index == 0 else "high",
                "f": "نامرتبط" if index == 0 else "مرتبط با خدمات مشاور",
                "g": "خرید" if index == 0 else "خدمات مشاور",
                "rs": "تناسب ندارد" if index == 0 else "تناسب مستقیم دارد",
                "a": "عدم پیگیری" if index == 0 else "بازبینی اسناد",
                "cf": 95,
                "m": "bulk_direct",
                "sr": "clear_no_match" if index == 0 else "strong_match",
                "cd": index == 1,
            })
        response = self.client.post(self.import_url, {"results": compact_results, "dry_run": False}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        counts = response.data["import"]["counts"]
        self.assertEqual(counts["imported"], 2)
        self.assertEqual(counts["drafts_created"], 1)
        self.assertEqual(counts["compact_results"], 1)
        self.assertEqual(NoticeAnalysisDraft.objects.count(), 1)
        self.assertEqual(ProcurementAnalysisRunItem.objects.filter(status="completed").count(), 2)
        compact_item = ProcurementAnalysisRunItem.objects.get(draft__isnull=True)
        self.assertTrue(compact_item.result_metadata["compact_only"])
''', encoding="utf-8")

workflow_path = ROOT / ".github/workflows/apply-bulk-chatgpt-analysis-v1.yml"
script_path = ROOT / "scripts/apply_bulk_chatgpt_analysis_v1.py"
workflow_path.unlink(missing_ok=True)
script_path.unlink(missing_ok=True)
print("bulk ChatGPT analysis v1 patch applied")
