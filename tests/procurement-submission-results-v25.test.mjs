import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const overlayPath = new URL("../app/procurement/ProcurementWorkflowActionsStableEnhancement.tsx", import.meta.url);
const wrapperPath = new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url);
const recommendedViewPath = new URL("../backend/procurement/views_recommended.py", import.meta.url);

test("mounts only the stable page-bounded workflow action overlay", async () => {
  const wrapper = await readFile(wrapperPath, "utf8");
  assert.match(wrapper, /ProcurementWorkflowActionsStableEnhancement/);
  assert.match(wrapper, /ProcurementManagementToolsStableEnhancement/);
  assert.doesNotMatch(wrapper, /ProcurementWorkspaceEnhancements/);
  assert.doesNotMatch(wrapper, /ProcurementSubmissionResultsEnhancements/);
});

test("allows submission without requiring an attached file", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /type="file" multiple/);
  assert.doesNotMatch(source, /multiple required/);
  assert.match(source, /JSON\.stringify\(\{ stage: "submitted" \}\)/);
  assert.match(source, /بدون فایل نیز ثبت ارسال انجام می‌شود/);
});

test("adds result registration for submitted notices and direct opportunities", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /state\.workflow === "submitted"/);
  assert.match(source, /actionButton\("ثبت نتیجه"\)/);
  assert.match(source, /const RESULTS_API = `\$\{PROCUREMENT_API\}\/opportunity-results`/);
  assert.match(source, /method: "PATCH"/);
  assert.match(source, /method: "POST"/);
  assert.match(source, /stage: resultOutcome/);
  assert.match(source, /opportunity: resultTarget\.id/);
  assert.match(source, /مورد به بخش «نتایج» منتقل شد/);
});

test("direct referrals do not keep the proposed workflow and human selection stays on the complete page", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.match(source, /state\.top === "direct" && state\.workflow === "recommended"/);
  assert.match(source, /کل ارجاعات مستقیم/);
  assert.match(source, /SELECTABLE_DIRECT_STAGES/);
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

test("workflow overlay has no polling, body observer, or archive fan-out", async () => {
  const source = await readFile(overlayPath, "utf8");
  assert.doesNotMatch(source, /MutationObserver/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /fetchAll/);
  assert.doesNotMatch(source, /maxPages/);
  assert.match(source, /MAX_PAGE_IDS|WORKFLOW_META_API/);
});
