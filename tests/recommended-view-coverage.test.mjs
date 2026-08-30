import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const v22 = fs.readFileSync("app/procurement/ProcurementWorkspaceV22.tsx", "utf8");
const dataClient = fs.readFileSync("app/procurement/procurementDataClient.ts", "utf8");
const baseWorkspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const page = fs.readFileSync("app/procurement/page.tsx", "utf8");
const backendView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("procurement page activates V23 with React-owned server pagination", () => {
  assert.match(page, /ProcurementWorkspaceV23/);
  assert.doesNotMatch(v23, /ProcurementPaginationStableEnhancement/);
  assert.match(v23, /ProcurementWorkspaceV22/);
  assert.match(v22, /ProcurementWorkspaceV21/);
  assert.match(baseWorkspace, /procurementDataClient\.staleWhileRevalidate/);
  assert.match(baseWorkspace, /pageSize:\s*noticePageSize/);
});

test("recommended coverage remains canonical without full background prefetch", () => {
  assert.doesNotMatch(v22, /RECOMMENDED_PAGE_LIMIT/);
  assert.doesNotMatch(v22, /fetchCompleteRecommended/);
  assert.match(baseWorkspace, /workflowCode\(noticeView\)/);
  assert.match(dataClient, /params\.set\("page_size"/);
  assert.match(dataClient, /\/api\/v1\/procurement\/ui\/notices\//);
  assert.match(backendView, /latest_effective_recommended_notice_ids/);
  assert.match(backendView, /NoticeAnalysisDraft/);
  assert.match(backendView, /Exists\(newer_draft\)/);
  assert.match(backendView, /analyzed_at__gt=OuterRef\("analyzed_at"\)/);
  assert.match(backendView, /created_at__gt=OuterRef\("created_at"\)/);
  assert.match(backendView, /id__gt=OuterRef\("id"\)/);
  assert.match(backendView, /has_newer_draft=False/);
  assert.match(backendView, /ReviewStatus\.REJECTED/);
  assert.match(backendView, /Subquery\(latest_effective_recommended_notice_ids\(\)\)/);
});

test("recent lists use the approved concise title while the compact server feed owns the date filter", () => {
  assert.match(baseWorkspace, /مناقصات اخیر/);
  assert.match(baseWorkspace, /استعلامات اخیر/);
  assert.match(baseWorkspace, /return view === "all" \? "recent" : view/);
  assert.match(dataClient, /params\.set\("workflow"/);
  assert.match(dataClient, /\/api\/v1\/procurement\/ui\/notices\//);
});

test("recommended lists are lazy page bounded and cache bounded", () => {
  assert.match(dataClient, /pageSize/);
  assert.match(dataClient, /cacheTtlMs \?\? 60_000/);
  assert.match(dataClient, /private readonly cache = new Map/);
  assert.match(dataClient, /staleWhileRevalidate/);
  assert.match(dataClient, /abortAllExcept/);
  assert.doesNotMatch(v22, /mergeUnique/);
  assert.doesNotMatch(v22, /injectedRecommendationIds/);
});
