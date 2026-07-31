import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("persistent analysis tools and UI expose the approved full queue controls", async () => {
  const tools = await readFile(new URL("../services/pdp_mcp/procurement_analysis_tools.py", import.meta.url), "utf8");
  const panel = await readFile(new URL("../app/procurement/ProcurementAnalysisCenterPanel.tsx", import.meta.url), "utf8");
  const tasks = await readFile(new URL("../backend/procurement/tasks_analysis_runs.py", import.meta.url), "utf8");

  for (const name of [
    "prepare_procurement_analysis_dataset",
    "get_procurement_analysis_dataset_status",
    "download_procurement_analysis_dataset",
    "import_procurement_analysis_results",
    "get_procurement_analysis_import_status",
    "start_full_pending_analysis",
    "start_incremental_analysis",
    "pause_procurement_analysis_run",
    "resume_procurement_analysis_run",
    "cancel_procurement_analysis_run",
    "get_procurement_analysis_run_status",
    "get_procurement_analysis_run_history",
  ]) {
    assert.match(tools, new RegExp(`async def ${name}\\(`));
  }
  assert.match(panel, /تحلیل همه موارد باقی‌مانده/);
  assert.match(panel, /اجرای دستی الآن/);
  assert.match(panel, /توقف موقت/);
  assert.match(panel, /لغو پردازش آینده/);
  assert.match(tasks, /dispatch_scheduled_analysis_run/);
  assert.match(tasks, /active_run\(\)/);
});


test("persistent result import remains draft-only and does not call contract or finance APIs", async () => {
  const service = await readFile(new URL("../backend/procurement/analysis_run_service.py", import.meta.url), "utf8");
  const tools = await readFile(new URL("../services/pdp_mcp/procurement_analysis_tools.py", import.meta.url), "utf8");
  assert.match(service, /ReviewStatus\.AI_DRAFT/);
  assert.match(service, /decision_is_draft/);
  assert.match(service, /requires_human_review/);
  assert.doesNotMatch(tools, /contracts\//);
  assert.doesNotMatch(tools, /receivables\//);
  assert.doesNotMatch(tools, /payment-receipts\//);
});
