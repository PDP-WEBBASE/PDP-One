import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("routes procurement through V15 while preserving V14", async () => {
  const page = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");
  const wrapper = await readFile(new URL("../app/procurement/ProcurementWorkspaceV15.tsx", import.meta.url), "utf8");

  assert.match(page, /ProcurementWorkspaceV15/);
  assert.match(wrapper, /ProcurementWorkspaceV14/);
  assert.match(wrapper, /OpportunityWorkflowPanel/);
  assert.match(wrapper, /مدیریت فرصت‌ها/);
});

test("loads live cases and notices and saves only explicit human changes", async () => {
  const panel = await readFile(new URL("../app/procurement/OpportunityWorkflowPanel.tsx", import.meta.url), "utf8");

  assert.match(panel, /procurement\/cases/);
  assert.match(panel, /procurement\/notices/);
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
