import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const overlayPath = new URL("../app/procurement/ProcurementWorkflowActionsStableEnhancement.tsx", import.meta.url);
const wrapperPath = new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url);
const recommendedViewPath = new URL("../backend/procurement/views_recommended.py", import.meta.url);

test("mounts the stable bounded submission and result workflow overlay", async () => {
  const wrapper = await readFile(wrapperPath, "utf8");
  assert.match(wrapper, /ProcurementWorkflowActionsStableEnhancement/);
  assert.match(wrapper, /<ProcurementWorkflowActionsStableEnhancement \/>/);
  assert.doesNotMatch(wrapper, /ProcurementSubmissionResultsEnhancements/);
  assert.doesNotMatch(wrapper, /ProcurementWorkspaceEnhancements/);
});

test("allows submission without requiring an attached file", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /for \(const file of files\)/);
  assert.match(source, /body: JSON\.stringify\(\{ stage: "submitted" \}\)/);
  assert.match(source, /مورد بدون فایل پیوست به «ارسال‌شده» منتقل شد/);
  assert.doesNotMatch(source, /required\s*=\s*true/);
});

test("adds result registration for submitted tenders inquiries and direct opportunities", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /state\.workflow === "submitted"/);
  assert.match(source, /actionButton\("ثبت نتیجه"\)/);
  assert.match(source, /const RESULTS_API = `\$\{PROCUREMENT_API\}\/opportunity-results`/);
  assert.match(source, /method: "PATCH"/);
  assert.match(source, /method: "POST"/);
  assert.match(source, /stage: resultOutcome/);
  assert.match(source, /opportunity: resultTarget\.id/);
  assert.match(source, /نتیجه ثبت شد و مورد به بخش «نتایج» منتقل شد/);
});

test("removes the proposed tab from direct referrals but keeps human selection from the complete list", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /state\.top === "direct" && state\.workflow === "recommended"/);
  assert.match(source, /کل ارجاعات مستقیم/);
  assert.match(source, /state\.workflow === "recent"/);
  assert.match(source, /updateDirectStage\(item, "selected"\)/);
});

test("allows a human to dismiss an AI recommendation without deleting the notice", async () => {
  const source = await readFile(overlayPath, "utf8");
  const backend = await readFile(recommendedViewPath, "utf8");
  assert.match(source, /حذف از پیشنهادی/);
  assert.match(source, /\$\{RECOMMENDED_API\}\/\$\{item\.id\}\/dismiss\//);
  assert.match(backend, /@action\(detail=True, methods=\["post"\], url_path="dismiss"\)/);
  assert.match(backend, /NoticeAnalysisDraft\.ReviewStatus\.REJECTED/);
  assert.match(backend, /procurement\.ai_recommendation\.dismiss/);
  assert.match(backend, /"notice_deleted": False/);
});
