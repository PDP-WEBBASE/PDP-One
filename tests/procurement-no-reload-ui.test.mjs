import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("ordinary procurement workflow mutations do not hard reload the page", async () => {
  const enhancements = await read("app/procurement/ProcurementWorkspaceEnhancements.tsx");
  const results = await read("app/procurement/ProcurementSubmissionResultsEnhancements.tsx");

  assert.doesNotMatch(enhancements, /window\.location\.reload\s*\(/);
  assert.doesNotMatch(results, /window\.location\.reload\s*\(/);
  assert.match(enhancements, /emitProcurementUiSync/);
  assert.match(results, /emitProcurementUiSync/);
  assert.match(enhancements, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(results, /PROCUREMENT_UI_SYNC_EVENT/);
});

test("selecting a recommended notice is row-local, optimistic and rollback-safe", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV13.tsx");
  const start = workspace.indexOf("async function selectNotice");
  const end = workspace.indexOf("async function submitDirect", start);
  assert.ok(start >= 0 && end > start, "selectNotice handler must exist");
  const handler = workspace.slice(start, end);

  assert.match(handler, /selectingNoticeIds/);
  assert.match(handler, /case_stage:\s*"selected"/);
  assert.match(handler, /setNotices/);
  assert.match(handler, /previous/);
  assert.match(handler, /procurementDataClient\.invalidate\(\)/);
  assert.match(handler, /setViewRefresh/);
  assert.match(handler, /setDashboardRefresh/);
  assert.doesNotMatch(handler, /setRefresh/);
  assert.doesNotMatch(handler, /location\.reload/);
});

test("ordinary workspace mutations avoid global refresh and use local reconciliation", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV13.tsx");

  for (const [name, next] of [
    ["async function toggleConnector", "async function runExtraction"],
    ["async function runExtraction", "async function saveAutomation"],
    ["async function submitDirect", "const urgencyOptions"],
  ]) {
    const start = workspace.indexOf(name);
    const end = workspace.indexOf(next, start);
    assert.ok(start >= 0 && end > start, `${name} handler must exist`);
    const handler = workspace.slice(start, end);
    assert.doesNotMatch(handler, /setRefresh/);
    assert.doesNotMatch(handler, /location\.reload/);
  }

  assert.match(workspace, /procurementDataClient\.invalidate/);
  assert.match(workspace, /setViewRefresh/);
  assert.match(workspace, /setDashboardRefresh/);
  assert.match(workspace, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(workspace, /bulkWorkspace/);
});

test("connectivity recovery is targeted and does not hard reload the procurement workspace", async () => {
  const v14 = await read("app/procurement/ProcurementWorkspaceV14.tsx");
  const reloads = v14.match(/window\.location\.reload\s*\(/g) || [];

  assert.equal(reloads.length, 0);
  assert.match(v14, /fetchFailure/);
  assert.match(v14, /retryFailedEndpoint/);
  assert.match(v14, /probeFailedEndpoint/);
  assert.match(v14, /تلاش مجدد/);
});

test("shared UI sync contract supports targeted and broad background reconciliation", async () => {
  const sync = await read("app/procurement/procurementUiSync.ts");
  assert.match(sync, /noticeId\?: string/);
  assert.match(sync, /directId\?: string/);
  assert.match(sync, /dashboard\?: boolean/);
  assert.match(sync, /bulkWorkspace\?: boolean/);
  assert.match(sync, /management\?: boolean/);
  assert.match(sync, /dispatchEvent/);
});
