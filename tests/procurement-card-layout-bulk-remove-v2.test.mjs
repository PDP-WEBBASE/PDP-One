import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync("app/procurement/ProcurementCardLayoutBulkRemoveV2.tsx", "utf8");
const baseWorkspace = readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const compact = readFileSync("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx", "utf8");
const listUx = readFileSync("app/procurement/ProcurementListUxRefinement.tsx", "utf8");
const actions = readFileSync("app/procurement/ProcurementWorkflowActionsStableEnhancement.tsx", "utf8");
const workspace = readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const urls = readFileSync("backend/procurement/urls.py", "utf8");
const backend = readFileSync("backend/procurement/views_bulk_workflow.py", "utf8");

test("follow-up card layout is mounted after the accepted list refinement", () => {
  assert.match(workspace, /import ProcurementCardLayoutBulkRemoveV2/);
  assert.ok(workspace.indexOf("<ProcurementCardLayoutBulkRemoveV2 />") > workspace.indexOf("<ProcurementListUxRefinement />"));
});

test("bulk remove covers current-page recent recommended selected submitted and results workflows", () => {
  for (const workflow of ["recent", "recommended", "selected", "submitted", "results"]) {
    assert.ok(component.includes(`\"${workflow}\"`), `missing bulk workflow ${workflow}`);
  }
  assert.match(component, /انتخاب همه این صفحه/);
  assert.match(component, /ui\/workflow\/remove-bulk\//);
  assert.match(component, /ui\/recommendations\/dismiss-bulk\//);
  assert.doesNotMatch(component, /dismiss_all/);
});

test("layout contract keeps compact metadata in three rows and clamps title by width", () => {
  assert.match(component, /pdp-v2-status-row/);
  assert.match(component, /pdp-v2-source-row/);
  assert.match(component, /pdp-v2-info-row/);
  assert.match(component, /text-overflow:ellipsis/);
  assert.match(component, /white-space:nowrap/);
  assert.doesNotMatch(component, /تعداد ردیف:/);
  assert.doesNotMatch(component, /موردی انتخاب نشده/);
  assert.match(component, /pdp-v2-filter-bar/);
  assert.match(component, /pdp-v2-stable-actions/);
});

test("notice card refinements bind by stable UUID before mutable title and employer text", () => {
  assert.match(baseWorkspace, /data-pdp-notice-id=\{item\.id\}/);
  assert.match(baseWorkspace, /data-pdp-direct-id=\{item\.id\}/);
  for (const source of [component, compact, listUx]) {
    assert.match(source, /dataset\.pdpNoticeId\s*===\s*(?:item\.)?id/);
  }
  assert.match(actions, /noticeById\.get\(article\.dataset\.pdpNoticeId\)/);
  assert.match(actions, /directById\.get\(article\.dataset\.pdpDirectId\)/);
});

test("unknown employer presentation cannot suppress stable workflow actions", () => {
  assert.match(actions, /function normalizeEmployer/);
  assert.match(actions, /normalized\s*===\s*"کارفرما نامشخص"\s*\?\s*""/);
  assert.match(actions, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(actions, /window\.addEventListener\(PROCUREMENT_UI_SYNC_EVENT, schedule\)/);
});

test("backend removal is bounded and non-destructive for view-only workflows", () => {
  assert.match(urls, /ui\/workflow\/remove-bulk\//);
  assert.match(backend, /MAX_BULK_IDS = 100/);
  assert.match(backend, /VIEW_DISMISS_WORKFLOWS = \{"recent", "submitted", "results"\}/);
  assert.match(backend, /notice_deleted": False/);
  assert.match(backend, /business_stage_changed": False/);
  assert.match(backend, /submission_documents\.exists\(\)/);
});

test("follow-up remains event-driven without polling or body-wide mutation observers", () => {
  assert.doesNotMatch(component, /setInterval\s*\(/);
  assert.doesNotMatch(component, /MutationObserver/);
  assert.match(component, /requestAnimationFrame/);
  assert.match(component, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(component, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
});
