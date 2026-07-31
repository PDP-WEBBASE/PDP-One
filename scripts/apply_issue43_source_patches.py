from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected source fragment not found in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "services/pdp_mcp/server.py",
    "from mcp.types import ToolAnnotations\n",
    "from mcp.types import ToolAnnotations\n\nfrom procurement_analysis_tools import register_procurement_analysis_tools\n",
)
replace_once(
    "services/pdp_mcp/server.py",
    "\n\n@mcp.tool(\n    description=\"Check whether PDP One, its PostgreSQL database, and the trial dataset are reachable.\"",
    "\n\nregister_procurement_analysis_tools(mcp, api)\n\n\n@mcp.tool(\n    description=\"Check whether PDP One, its PostgreSQL database, and the trial dataset are reachable.\"",
)
replace_once(
    "backend/procurement/views_analysis_runs.py",
    "from django.http import FileResponse\n",
    "from django.conf import settings\nfrom django.http import FileResponse\n",
)
replace_once(
    "backend/procurement/views_analysis_runs.py",
    "json.dumps(results, ensure_ascii=False, sort_keys=True).encode(\"utf-8\")",
    "json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\")).encode(\"utf-8\")",
)
replace_once(
    "backend/procurement/analysis_run_service.py",
    "@transaction.atomic\ndef import_result_records(",
    "def import_result_records(",
)
replace_once(
    "tests/rendered-html.test.mjs",
    'test("routes procurement through V20 while preserving V19 to V13", async () => {\n  const page = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");\n  const versions = new Map();\n  for (let version = 13; version <= 20; version += 1) {\n    versions.set(version, await readFile(new URL(`../app/procurement/ProcurementWorkspaceV${version}.tsx`, import.meta.url), "utf8"));\n  }\n  assert.match(page, /ProcurementWorkspaceV20/);\n  for (let version = 20; version > 13; version -= 1) {\n    assert.match(versions.get(version), new RegExp(`ProcurementWorkspaceV${version - 1}`));\n  }\n  assert.match(versions.get(20), /AutomationControlPanel/);',
    'test("routes procurement through V21 while preserving V20 to V13", async () => {\n  const page = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");\n  const versions = new Map();\n  for (let version = 13; version <= 21; version += 1) {\n    versions.set(version, await readFile(new URL(`../app/procurement/ProcurementWorkspaceV${version}.tsx`, import.meta.url), "utf8"));\n  }\n  assert.match(page, /ProcurementWorkspaceV21/);\n  for (let version = 21; version > 13; version -= 1) {\n    assert.match(versions.get(version), new RegExp(`ProcurementWorkspaceV${version - 1}`));\n  }\n  assert.match(versions.get(21), /ProcurementAnalysisCenterPanel/);\n  assert.match(versions.get(20), /AutomationControlPanel/);',
)
