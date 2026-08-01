from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
server_path = ROOT / "services/pdp_mcp/server.py"
text = server_path.read_text(encoding="utf-8")

if "import hashlib\n" not in text:
    text = text.replace("import os\n", "import hashlib\nimport os\n", 1)

old = '''async def save_analysis_draft(title: str, summary: str, source_record_ids: list[str]) -> dict:
    payload = {
        "title": title,
        "summary": summary,
        "source_record_ids": source_record_ids,
        "model_label": "ChatGPT",
        "review_status": "ai_draft",
    }
    return {"report": await api("POST", "analysis-reports/", json=payload), "requires_human_review": True}
'''

new = '''async def save_analysis_draft(title: str, summary: str, source_record_ids: list[str]) -> dict:
    # Compatibility bridge for ChatGPT apps whose cached schema predates the
    # dedicated persistent-analysis tools. The official tools remain the
    # primary interface; this bridge keeps existing installed apps operable
    # until their MCP schema is rescanned.
    if title.startswith("__PDPONE_ANALYSIS_"):
        try:
            options = json.loads(summary or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Persistent analysis control summary must be valid JSON.") from exc
        if not isinstance(options, dict):
            raise ValueError("Persistent analysis control summary must be a JSON object.")

        def required_identifier(name: str) -> str:
            value = str(options.get(name) or (source_record_ids[0] if source_record_ids else "")).strip()
            if not value:
                raise ValueError(f"{name} is required.")
            return value

        if title == "__PDPONE_ANALYSIS_START_FULL__":
            result = await api(
                "POST",
                "procurement/analysis/runs/full-pending/start/",
                json={
                    "trigger": "manual_chatgpt",
                    "scope": "all_pending",
                    "include_expired": bool(options.get("include_expired", False)),
                    "include_previously_analyzed": bool(options.get("include_previously_analyzed", False)),
                    "shard_size": max(1, min(int(options.get("shard_size", 250)), 5000)),
                    "deep_analysis_batch_size": max(1, min(int(options.get("deep_analysis_batch_size", 25)), 250)),
                    "parallel_workers": max(1, min(int(options.get("parallel_workers", 4)), 16)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_START_INCREMENTAL__":
            result = await api(
                "POST",
                "procurement/analysis/runs/incremental/start/",
                json={
                    "trigger": "manual_chatgpt",
                    "scope": "all_pending",
                    "include_expired": bool(options.get("include_expired", False)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_STATUS__":
            run_id = str(options.get("run_id") or (source_record_ids[0] if source_record_ids else "")).strip()
            result = await api(
                "GET",
                f"procurement/analysis/runs/{run_id}/" if run_id else "procurement/analysis/runs/current/",
            )
        elif title == "__PDPONE_ANALYSIS_HISTORY__":
            result = await api(
                "GET",
                "procurement/analysis/runs/history/",
                params={"limit": max(1, min(int(options.get("limit", 25)), 100))},
            )
        elif title == "__PDPONE_ANALYSIS_CLAIM__":
            run_id = required_identifier("run_id")
            result = await api(
                "POST",
                f"procurement/analysis/runs/{run_id}/claim/",
                json={
                    "worker_id": str(options.get("worker_id", "chatgpt-compatibility-bridge"))[:120],
                    "limit": max(1, min(int(options.get("limit", 25)), 250)),
                    "lease_seconds": max(60, min(int(options.get("lease_seconds", 900)), 3600)),
                },
            )
        elif title == "__PDPONE_ANALYSIS_DATASET_PREPARE__":
            run_id = required_identifier("run_id")
            result = await api(
                "POST",
                f"procurement/analysis/runs/{run_id}/datasets/prepare/",
                json={
                    "scope": str(options.get("scope", "all_pending")),
                    "shard_size": max(1, min(int(options.get("shard_size", 250)), 5000)),
                    "compression": str(options.get("compression", "gzip")),
                },
            )
        elif title == "__PDPONE_ANALYSIS_DATASET_STATUS__":
            dataset_id = required_identifier("dataset_id")
            result = await api("GET", f"procurement/analysis/datasets/{dataset_id}/")
        elif title == "__PDPONE_ANALYSIS_IMPORT__":
            run_id = required_identifier("run_id")
            results = options.get("results") or []
            if not isinstance(results, list):
                raise ValueError("results must be a JSON list.")
            canonical = json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload = {
                "results": results,
                "result_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "dry_run": bool(options.get("dry_run", False)),
            }
            if options.get("dataset_id"):
                payload["dataset_id"] = str(options["dataset_id"])
            result = await api("POST", f"procurement/analysis/runs/{run_id}/results/import/", json=payload)
        elif title == "__PDPONE_ANALYSIS_IMPORT_STATUS__":
            import_id = required_identifier("import_id")
            result = await api("GET", f"procurement/analysis/imports/{import_id}/")
        elif title == "__PDPONE_ANALYSIS_PAUSE__":
            run_id = required_identifier("run_id")
            result = await api("POST", f"procurement/analysis/runs/{run_id}/pause/", json={})
        elif title == "__PDPONE_ANALYSIS_RESUME__":
            run_id = required_identifier("run_id")
            result = await api("POST", f"procurement/analysis/runs/{run_id}/resume/", json={})
        else:
            raise ValueError("Unknown persistent analysis compatibility command.")
        return {
            "persistent_analysis": result,
            "compatibility_bridge": True,
            "requires_human_review": True,
            "draft_only": True,
        }

    payload = {
        "title": title,
        "summary": summary,
        "source_record_ids": source_record_ids,
        "model_label": "ChatGPT",
        "review_status": "ai_draft",
    }
    return {"report": await api("POST", "analysis-reports/", json=payload), "requires_human_review": True}
'''

if old not in text:
    raise SystemExit("save_analysis_draft block not found")
server_path.write_text(text.replace(old, new, 1), encoding="utf-8")

contract_path = ROOT / "tests/persistent-analysis-contract.test.mjs"
contract = contract_path.read_text(encoding="utf-8")
needle = '''  assert.doesNotMatch(tools, /payment-receipts\\//);
});
'''
replacement = '''  assert.doesNotMatch(tools, /payment-receipts\\//);
});


test("cached ChatGPT app schema has a safe persistent-analysis compatibility bridge", async () => {
  const server = await readFile(new URL("../services/pdp_mcp/server.py", import.meta.url), "utf8");
  for (const command of [
    "__PDPONE_ANALYSIS_START_FULL__",
    "__PDPONE_ANALYSIS_START_INCREMENTAL__",
    "__PDPONE_ANALYSIS_STATUS__",
    "__PDPONE_ANALYSIS_HISTORY__",
    "__PDPONE_ANALYSIS_CLAIM__",
    "__PDPONE_ANALYSIS_DATASET_PREPARE__",
    "__PDPONE_ANALYSIS_DATASET_STATUS__",
    "__PDPONE_ANALYSIS_IMPORT__",
    "__PDPONE_ANALYSIS_IMPORT_STATUS__",
    "__PDPONE_ANALYSIS_PAUSE__",
    "__PDPONE_ANALYSIS_RESUME__",
  ]) {
    assert.match(server, new RegExp(command));
  }
  assert.match(server, /compatibility_bridge/);
  assert.match(server, /draft_only/);
  assert.doesNotMatch(server.slice(server.indexOf("if title.startswith"), server.indexOf("payload = {", server.indexOf("if title.startswith") + 1)), /contracts\\//);
});
'''
if needle not in contract:
    raise SystemExit("persistent analysis contract insertion point not found")
contract_path.write_text(contract.replace(needle, replacement, 1), encoding="utf-8")

print("Persistent analysis compatibility bridge applied")
