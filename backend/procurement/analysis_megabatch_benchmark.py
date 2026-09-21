from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .analysis_run_service import _compact_basis
from .analysis_utils import notice_basis_hash
from .models_analysis_runs import ProcurementAnalysisRun, ProcurementAnalysisRunItem


BENCHMARK_SCHEMA = "pdp-one.analysis-megabatch-benchmark.v1"
ALLOWED_STAGE_SIZES = (50, 250, 500, 1000, 2000, 5000)
MAX_CORPUS_SIZE = 5000


def _root() -> Path:
    path = Path(settings.MEDIA_ROOT) / "procurement-analysis-benchmarks"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _benchmark_dir(benchmark_id: str) -> Path:
    value = str(benchmark_id).strip()
    try:
        normalized = str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Benchmark ID نامعتبر است.") from exc
    path = (_root() / normalized).resolve()
    if path.parent != _root():
        raise ValueError("مسیر Benchmark نامعتبر است.")
    return path


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise ValueError("Benchmark پیدا نشد.")
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _manifest_path(benchmark_id: str) -> Path:
    return _benchmark_dir(benchmark_id) / "manifest.json"


def _stage_path(benchmark_id: str, stage_size: int) -> Path:
    return _benchmark_dir(benchmark_id) / f"stage-{int(stage_size)}.json"


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "i": "run_item_id",
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
        "me": "matched_experience",
        "rn": "risk_notes",
        "mi": "missing_information",
        "cf": "confidence",
        "m": "analysis_mode",
        "sr": "screening_reason",
        "u": "urgency",
        "ot": "business_opportunity_type",
        "otr": "business_opportunity_type_reason",
        "otc": "business_opportunity_type_confidence",
    }
    normalized = dict(result)
    for short_key, full_key in key_map.items():
        if full_key not in normalized and short_key in result:
            normalized[full_key] = result[short_key]
    return normalized


def create_megabatch_benchmark(
    *,
    run_id: str,
    corpus_size: int = MAX_CORPUS_SIZE,
) -> dict[str, Any]:
    requested = max(1, min(int(corpus_size), MAX_CORPUS_SIZE))
    run = ProcurementAnalysisRun.objects.select_related("context_snapshot").get(pk=run_id)
    queryset = (
        ProcurementAnalysisRunItem.objects.filter(run=run)
        .select_related("notice", "run", "run__context_snapshot")
        .prefetch_related("notice__source_links__source_notice")
        .order_by("sequence")
    )
    records: list[dict[str, Any]] = []
    skipped_changed = 0
    for item in queryset.iterator(chunk_size=250):
        current_hash = notice_basis_hash(item.notice)
        if current_hash != item.notice_content_hash or item.context_hash != run.context_snapshot.content_hash:
            skipped_changed += 1
            continue
        records.append(
            {
                "i": str(item.id),
                "n": str(item.notice_id),
                "c": item.notice_content_hash,
                "ar": item.analysis_reason,
                "dp": item.deadline_priority,
                "b": _compact_basis(item.notice),
            }
        )
        if len(records) >= requested:
            break
    if len(records) < requested:
        raise ValueError(
            f"برای Corpus ثابت {requested} رکورد سالم کافی نیست؛ فقط {len(records)} رکورد ثابت پیدا شد."
        )

    benchmark_id = str(uuid.uuid4())
    manifest = {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_id": benchmark_id,
        "run_id": str(run.id),
        "created_at": timezone.now().isoformat(),
        "context": {
            "id": str(run.context_snapshot_id),
            "version": run.context_snapshot.version,
            "hash": run.context_snapshot.content_hash,
        },
        "corpus_size": len(records),
        "skipped_changed_records": skipped_changed,
        "stages": list(ALLOWED_STAGE_SIZES),
        "records": records,
    }
    manifest["corpus_sha256"] = _canonical_sha(
        {
            "context": manifest["context"],
            "records": records,
        }
    )
    _atomic_json(_manifest_path(benchmark_id), manifest)
    return benchmark_manifest_summary(manifest)


def benchmark_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": manifest["schema"],
        "benchmark_id": manifest["benchmark_id"],
        "run_id": manifest["run_id"],
        "created_at": manifest["created_at"],
        "context": manifest["context"],
        "corpus_size": manifest["corpus_size"],
        "corpus_sha256": manifest["corpus_sha256"],
        "stages": manifest["stages"],
        "skipped_changed_records": manifest.get("skipped_changed_records", 0),
        "production_mutation": False,
        "draft_only": True,
    }


def get_megabatch_benchmark_batch(
    *,
    benchmark_id: str,
    stage_size: int,
    offset: int = 0,
) -> dict[str, Any]:
    size = int(stage_size)
    if size not in ALLOWED_STAGE_SIZES:
        raise ValueError("Stage size خارج از مقادیر مصوب Benchmark است.")
    manifest = _read_json(_manifest_path(benchmark_id))
    corpus_size = int(manifest["corpus_size"])
    start = max(0, int(offset))
    if start >= corpus_size:
        return {
            "benchmark_id": benchmark_id,
            "stage_size": size,
            "offset": start,
            "count": 0,
            "corpus_size": corpus_size,
            "corpus_sha256": manifest["corpus_sha256"],
            "context": manifest["context"],
            "items": [],
            "complete_after_this_batch": True,
        }
    if start % size != 0:
        raise ValueError("Offset باید مضربی از Stage size باشد.")

    selected = manifest["records"][start : min(start + size, corpus_size)]
    canonical = json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "format": "pdp-one.megabatch-benchmark.v1",
        "benchmark_id": benchmark_id,
        "stage_size": size,
        "offset": start,
        "count": len(selected),
        "corpus_size": corpus_size,
        "corpus_sha256": manifest["corpus_sha256"],
        "context": manifest["context"],
        "items": selected,
        "payload_chars": len(canonical),
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "complete_after_this_batch": start + len(selected) >= corpus_size,
        "production_mutation": False,
    }


def submit_megabatch_benchmark_results(
    *,
    benchmark_id: str,
    stage_size: int,
    offset: int,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    size = int(stage_size)
    if size not in ALLOWED_STAGE_SIZES:
        raise ValueError("Stage size خارج از مقادیر مصوب Benchmark است.")
    manifest = _read_json(_manifest_path(benchmark_id))
    start = max(0, int(offset))
    if start % size != 0:
        raise ValueError("Offset باید مضربی از Stage size باشد.")
    expected = manifest["records"][start : min(start + size, int(manifest["corpus_size"]))]
    if len(results) != len(expected):
        raise ValueError(
            f"تعداد نتایج ({len(results)}) با تعداد ورودی همان Batch ({len(expected)}) برابر نیست."
        )

    expected_by_id = {str(item["i"]): item for item in expected}
    normalized_results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in results:
        result = _normalize_result(dict(raw))
        item_id = str(result.get("run_item_id") or "")
        if not item_id or item_id not in expected_by_id:
            raise ValueError("Result شامل Run Item خارج از Batch ثابت Benchmark است.")
        if item_id in seen:
            raise ValueError("Run Item تکراری در نتایج Benchmark وجود دارد.")
        seen.add(item_id)
        expected_item = expected_by_id[item_id]
        if str(result.get("notice_id") or "") != str(expected_item["n"]):
            raise ValueError("Notice ID با Corpus ثابت Benchmark تطابق ندارد.")
        if result.get("notice_content_hash") and str(result["notice_content_hash"]) != str(expected_item["c"]):
            raise ValueError("Notice Content Hash با Corpus ثابت Benchmark تطابق ندارد.")
        if str(result.get("context_hash") or "") != str(manifest["context"]["hash"]):
            raise ValueError("Context Hash نتیجه با Benchmark تطابق ندارد.")
        if "is_recommended" not in result:
            raise ValueError("هر Result باید is_recommended داشته باشد.")
        result["run_item_id"] = item_id
        result["notice_id"] = str(expected_item["n"])
        result["notice_content_hash"] = str(expected_item["c"])
        result["context_hash"] = str(manifest["context"]["hash"])
        result["is_recommended"] = bool(result["is_recommended"])
        if "score" in result:
            result["score"] = max(0, min(int(result.get("score") or 0), 100))
        if "confidence" in result:
            result["confidence"] = max(0.0, min(float(result.get("confidence") or 0), 100.0))
        normalized_results.append(result)

    stage_path = _stage_path(benchmark_id, size)
    stage = (
        _read_json(stage_path)
        if stage_path.is_file()
        else {
            "schema": BENCHMARK_SCHEMA,
            "benchmark_id": benchmark_id,
            "stage_size": size,
            "corpus_sha256": manifest["corpus_sha256"],
            "results": {},
            "submissions": [],
        }
    )
    stored = dict(stage.get("results") or {})
    for result in normalized_results:
        item_id = result["run_item_id"]
        if item_id in stored and _canonical_sha(stored[item_id]) != _canonical_sha(result):
            raise ValueError("برای این Run Item قبلاً Result متفاوتی در همین Stage ثبت شده است.")
        stored[item_id] = result
    stage["results"] = stored
    stage.setdefault("submissions", []).append(
        {
            "offset": start,
            "count": len(normalized_results),
            "result_sha256": _canonical_sha(normalized_results),
            "submitted_at": timezone.now().isoformat(),
        }
    )
    _atomic_json(stage_path, stage)
    return _stage_summary(manifest, stage)


def _needs_information(result: dict[str, Any]) -> bool:
    missing = result.get("missing_information")
    if isinstance(missing, str):
        missing = missing.strip()
    screening = str(result.get("screening_reason") or "").strip().lower()
    return bool(missing) or screening in {"needs_information", "needs-info", "needs_info"}


def _urgent(result: dict[str, Any]) -> bool:
    values = {
        str(result.get("priority") or "").strip().lower(),
        str(result.get("urgency") or "").strip().lower(),
    }
    return bool(values & {"urgent", "critical"})


def _stage_summary(manifest: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    results = list((stage.get("results") or {}).values())
    recommended_ids = sorted(
        str(value["run_item_id"]) for value in results if bool(value.get("is_recommended"))
    )
    needs_information_ids = sorted(
        str(value["run_item_id"]) for value in results if _needs_information(value)
    )
    urgent_ids = sorted(str(value["run_item_id"]) for value in results if _urgent(value))
    complete = len(results) == int(manifest["corpus_size"])
    return {
        "stage_size": int(stage["stage_size"]),
        "processed": len(results),
        "corpus_size": int(manifest["corpus_size"]),
        "complete": complete,
        "recommended": len(recommended_ids),
        "not_recommended": len(results) - len(recommended_ids),
        "needs_information": len(needs_information_ids),
        "urgent": len(urgent_ids),
        "recommended_ids": recommended_ids if complete else [],
        "result_sha256": _canonical_sha(stage.get("results") or {}),
        "submissions": len(stage.get("submissions") or []),
    }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _comparison(
    baseline_stage: dict[str, Any],
    candidate_stage: dict[str, Any],
) -> dict[str, Any]:
    baseline = dict(baseline_stage.get("results") or {})
    candidate = dict(candidate_stage.get("results") or {})
    if not baseline or set(baseline) != set(candidate):
        return {"available": False}

    baseline_recommended = {key for key, value in baseline.items() if bool(value.get("is_recommended"))}
    candidate_recommended = {key for key, value in candidate.items() if bool(value.get("is_recommended"))}
    union = baseline_recommended | candidate_recommended
    intersection = baseline_recommended & candidate_recommended
    added = sorted(candidate_recommended - baseline_recommended)
    removed = sorted(baseline_recommended - candidate_recommended)

    score_deltas: list[float] = []
    confidence_deltas: list[float] = []
    reason_exact = 0
    action_exact = 0
    for key in baseline:
        left, right = baseline[key], candidate[key]
        left_score, right_score = _number(left.get("score")), _number(right.get("score"))
        if left_score is not None and right_score is not None:
            score_deltas.append(abs(left_score - right_score))
        left_conf, right_conf = _number(left.get("confidence")), _number(right.get("confidence"))
        if left_conf is not None and right_conf is not None:
            confidence_deltas.append(abs(left_conf - right_conf))
        if str(left.get("reason") or "").strip() == str(right.get("reason") or "").strip():
            reason_exact += 1
        if str(left.get("recommended_action") or "").strip() == str(right.get("recommended_action") or "").strip():
            action_exact += 1

    total = len(baseline)
    return {
        "available": True,
        "baseline_recommended": len(baseline_recommended),
        "candidate_recommended": len(candidate_recommended),
        "recommendation_set_intersection": len(intersection),
        "recommendation_set_union": len(union),
        "recommendation_set_overlap_jaccard": round(len(intersection) / len(union), 6) if union else 1.0,
        "recommendation_drift_count": len(added) + len(removed),
        "recommendation_added_ids": added,
        "recommendation_removed_ids": removed,
        "mean_abs_score_drift": round(sum(score_deltas) / len(score_deltas), 6) if score_deltas else None,
        "max_abs_score_drift": max(score_deltas) if score_deltas else None,
        "mean_abs_confidence_drift": (
            round(sum(confidence_deltas) / len(confidence_deltas), 6) if confidence_deltas else None
        ),
        "max_abs_confidence_drift": max(confidence_deltas) if confidence_deltas else None,
        "reason_exact_match_rate": round(reason_exact / total, 6) if total else 1.0,
        "recommended_action_exact_match_rate": round(action_exact / total, 6) if total else 1.0,
    }


def megabatch_benchmark_status(benchmark_id: str) -> dict[str, Any]:
    manifest = _read_json(_manifest_path(benchmark_id))
    stages: list[dict[str, Any]] = []
    stage_objects: dict[int, dict[str, Any]] = {}
    for size in ALLOWED_STAGE_SIZES:
        path = _stage_path(benchmark_id, size)
        if path.is_file():
            stage = _read_json(path)
            stage_objects[size] = stage
            stages.append(_stage_summary(manifest, stage))
        else:
            stages.append(
                {
                    "stage_size": size,
                    "processed": 0,
                    "corpus_size": int(manifest["corpus_size"]),
                    "complete": False,
                    "recommended": 0,
                    "not_recommended": 0,
                    "needs_information": 0,
                    "urgent": 0,
                    "recommended_ids": [],
                    "submissions": 0,
                }
            )

    baseline = stage_objects.get(50)
    comparisons: dict[str, Any] = {}
    if baseline and len(baseline.get("results") or {}) == int(manifest["corpus_size"]):
        for size, stage in stage_objects.items():
            if size == 50:
                continue
            if len(stage.get("results") or {}) == int(manifest["corpus_size"]):
                comparisons[str(size)] = _comparison(baseline, stage)

    return {
        "manifest": benchmark_manifest_summary(manifest),
        "stages": stages,
        "comparisons_to_50": comparisons,
        "production_mutation": False,
    }
