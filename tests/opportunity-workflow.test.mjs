import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("routes procurement through V22 while preserving the V15 opportunity workflow", async () => {
  const page = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");
  const v22 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV22.tsx", import.meta.url), "utf8");
  const v21 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV21.tsx", import.meta.url), "utf8");
  const v20 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV20.tsx", import.meta.url), "utf8");
  const v19 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV19.tsx", import.meta.url), "utf8");
  const v18 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV18.tsx", import.meta.url), "utf8");
  const v17 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV17.tsx", import.meta.url), "utf8");
  const v16 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV16.tsx", import.meta.url), "utf8");
  const v15 = await readFile(new URL("../app/procurement/ProcurementWorkspaceV15.tsx", import.meta.url), "utf8");

  assert.match(page, /ProcurementWorkspaceV22/);
  assert.match(v22, /ProcurementWorkspaceV21/);
  assert.match(v21, /ProcurementWorkspaceV20/);
  assert.match(v21, /ProcurementAnalysisCenterPanel/);
  assert.match(v20, /ProcurementWorkspaceV19/);
  assert.match(v19, /ProcurementWorkspaceV18/);
  assert.match(v18, /ProcurementWorkspaceV17/);
  assert.match(v17, /ProcurementWorkspaceV16/);
  assert.match(v16, /ProcurementWorkspaceV15/);
  assert.match(v16, /AIReviewCenterPanel/);
  assert.match(v15, /ProcurementWorkspaceV14/);
  assert.match(v15, /OpportunityWorkflowPanel/);
  assert.match(v15, /مدیریت فرصت‌ها/);
});

test("loads live cases and notices and saves only explicit human changes", async () => {
  const panel = await readFile(new URL("../app/procurement/OpportunityWorkflowPanel.tsx", import.meta.url), "utf8");

  assert.match(panel, /const PROCUREMENT_API = `\$\{API_BASE\}\/procurement`/);
  assert.match(panel, /const CASES_API = `\$\{PROCUREMENT_API\}\/cases`/);
  assert.match(panel, /fetchAll<RawCase>\(`\$\{CASES_API\}\/\?ordering=-updated_at`\)/);
  assert.match(panel, /fetchAll<NoticeSummary>\(`\$\{PROCUREMENT_API\}\/notices\/\?ordering=-last_seen_at`\)/);
  assert.match(panel, /method:\s*"PATCH"/);
  assert.match(panel, /X-CSRFToken/);
  assert.match(panel, /next_action_due/);
  assert.match(panel, /decision_reason/);
  assert.match(panel, /progress/);
  assert.match(panel, /do_not_participate/);
  assert.match(panel, /ثبت دلیل الزامی است/);
  assert.match(panel, /هر تغییر فقط با ذخیره صریح کاربر انجام می‌شود/);
  assert.doesNotMatch(panel, /contracts\//);
  assert.doesNotMatch(panel, /payment-receipts/);
  assert.doesNotMatch(panel, /method:\s*"POST"/);
});

test("limits visible stage transitions to the approved human workflow", async () => {
  const panel = await readFile(new URL("../app/procurement/OpportunityWorkflowPanel.tsx", import.meta.url), "utf8");

  assert.match(panel, /selected:\s*\["evaluating",\s*"do_not_participate"\]/);
  assert.match(panel, /evaluating:\s*\["participate",\s*"do_not_participate"\]/);
  assert.match(panel, /participate:\s*\["preparing"\]/);
  assert.match(panel, /preparing:\s*\["ready_to_submit"\]/);
  assert.match(panel, /ready_to_submit:\s*\["submitted"\]/);
  assert.match(panel, /submitted:\s*\["awaiting_result"\]/);
  assert.match(panel, /awaiting_result:\s*\["won",\s*"lost",\s*"cancelled",\s*"renewed"\]/);
});
