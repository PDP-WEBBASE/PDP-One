import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const composition = read("app/procurement/ProcurementWorkspaceV23.tsx");
const workspace = read("app/procurement/ProcurementWorkspaceV13.tsx");
const dataClient = read("app/procurement/procurementDataClient.ts");
const pagination = read("app/procurement/ProcurementPaginationStableEnhancement.tsx");
const compact = read("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx");
const actions = read("app/procurement/ProcurementWorkflowActionsStableEnhancement.tsx");
const managementTools = read("app/procurement/ProcurementManagementToolsStableEnhancement.tsx");
const viewState = read("app/procurement/procurementStableViewState.ts");
const fullTitle = read("app/procurement/ProcurementFullTitleEnhancement.tsx");
const workflowMetadata = read("backend/procurement/views_workflow_ui.py");

test("V23 mounts the React-owned bounded workspace and no legacy high-volume fetch controller", () => {
  assert.doesNotMatch(composition, /ProcurementPaginationStableEnhancement/);
  assert.match(composition, /ProcurementWorkspaceV22/);
  assert.match(composition, /ProcurementWorkflowActionsStableEnhancement/);
  assert.match(composition, /ProcurementManagementToolsStableEnhancement/);
  assert.match(composition, /import\("\.\/ProcurementCompactWorkspaceStableEnhancement"\)/);
  assert.match(composition, /ssr:\s*false/);
  assert.match(workspace, /procurementDataClient\.staleWhileRevalidate/);
  assert.match(dataClient, /abortAllExcept/);
  assert.doesNotMatch(composition, /ProcurementWorkspaceEnhancements/);
  assert.doesNotMatch(composition, /ProcurementSubmissionResultsEnhancements/);
  assert.doesNotMatch(composition, /ProcurementTabCacheEnhancement/);
  assert.doesNotMatch(composition, /ProcurementPaginationIntegrityEnhancement/);
});

test("top and workflow state comes from captured user intent, never class-name guessing", () => {
  assert.match(workspace, /setProcurementStableViewState\(\{ top: tab, workflow \}\)/);
  assert.doesNotMatch(viewState, /className/);
  assert.doesNotMatch(viewState, /MutationObserver/);
});

test("list loading is page-bounded, cached, and stale responses are context-checked", () => {
  assert.match(workspace, /type PageSize = 30 \| 50 \| 100/);
  assert.match(workspace, /pageSize:\s*noticePageSize/);
  assert.match(dataClient, /cacheTtlMs/);
  assert.match(dataClient, /Stale procurement response discarded/);
  assert.match(dataClient, /abortAllExcept/);
  assert.doesNotMatch(dataClient, /MutationObserver/);
  assert.doesNotMatch(dataClient, /setInterval/);
});

test("workflow actions are current-page only and never scan the archive", () => {
  assert.match(actions, /WORKFLOW_META_API/);
  assert.match(actions, /slice\(0, 100\)/);
  assert.doesNotMatch(actions, /MutationObserver/);
  assert.doesNotMatch(actions, /setInterval/);
  assert.doesNotMatch(actions, /fetchAll/);
  assert.doesNotMatch(actions, /maxPages/);
  assert.match(workflowMetadata, /MAX_PAGE_IDS = 100/);
  assert.match(workflowMetadata, /notice_id__in=notice_ids/);
  assert.match(workflowMetadata, /id__in=direct_ids/);
});

test("management tools no longer observe or rescan the whole document", () => {
  assert.match(managementTools, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(managementTools, /ابزارهای مدیریتی زیرسامانه/);
  assert.doesNotMatch(managementTools, /MutationObserver/);
  assert.doesNotMatch(managementTools, /setInterval/);
});

test("compact and title presentation are event-driven without DOM observation loops", () => {
  assert.match(compact, /pdpCompactSignature/);
  assert.match(compact, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(compact, /requestAnimationFrame/);
  assert.doesNotMatch(compact, /MutationObserver/);
  assert.doesNotMatch(compact, /setInterval/);
  assert.doesNotMatch(compact, /window\.fetch\s*=/);
  assert.match(fullTitle, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(fullTitle, /requestAnimationFrame/);
  assert.doesNotMatch(fullTitle, /MutationObserver/);
});

test("compact server feed preserves V13 recent/recommended predicates", () => {
  assert.match(workspace, /workflowCode\(noticeView\)/);
  assert.match(workspace, /noticeType:/);
  assert.match(dataClient, /workflow/);
  assert.match(dataClient, /\/api\/v1\/procurement\/ui\/notices\//);
});
