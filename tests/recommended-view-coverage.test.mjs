import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const v22 = fs.readFileSync("app/procurement/ProcurementWorkspaceV22.tsx", "utf8");
const pagination = fs.readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const baseWorkspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const page = fs.readFileSync("app/procurement/page.tsx", "utf8");
const backendView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("procurement page activates V23 with stable server pagination", () => {
  assert.match(page, /ProcurementWorkspaceV23/);
  assert.match(v23, /ProcurementPaginationStableEnhancement/);
  assert.match(v23, /ProcurementWorkspaceV22/);
  assert.match(v22, /ProcurementWorkspaceV21/);
  assert.doesNotMatch(v23, /<ProcurementPaginationEnhancement \/>/);
});

test("recommended coverage remains canonical without full background prefetch", () => {
  assert.doesNotMatch(v22, /RECOMMENDED_PAGE_LIMIT/);
  assert.doesNotMatch(v22, /fetchCompleteRecommended/);
  assert.match(pagination, /recommended-notices/);
  assert.match(pagination, /params\.set\("page_size", String\(pageState\.pageSize\)\)/);
  assert.match(pagination, /COMPACT_NOTICE_PATH/);
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
  assert.match(pagination, /return "recent"/);
  assert.match(pagination, /params\.set\("workflow", workflowCode\(state\.workflow\)\)/);
  assert.match(pagination, /COMPACT_NOTICE_PATH/);
});

test("recommended lists are lazy page bounded and cache bounded", () => {
  assert.match(pagination, /emptyCollectionResponse/);
  assert.match(pagination, /next:\s*null/);
  assert.match(pagination, /type PageSize = 30 \| 50 \| 100/);
  assert.match(pagination, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(pagination, /MAX_CACHE_ENTRIES = 60/);
  assert.doesNotMatch(v22, /mergeUnique/);
  assert.doesNotMatch(v22, /injectedRecommendationIds/);
});
