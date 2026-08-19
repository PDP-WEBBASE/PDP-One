import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const v22 = fs.readFileSync("app/procurement/ProcurementWorkspaceV22.tsx", "utf8");
const pagination = fs.readFileSync("app/procurement/ProcurementPaginationEnhancement.tsx", "utf8");
const baseWorkspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const page = fs.readFileSync("app/procurement/page.tsx", "utf8");
const backendView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("procurement page activates V23 with server pagination", () => {
  assert.match(page, /ProcurementWorkspaceV23/);
  assert.match(v23, /ProcurementPaginationEnhancement/);
  assert.match(v23, /ProcurementWorkspaceV22/);
  assert.match(v22, /ProcurementWorkspaceV21/);
});

test("recommended coverage remains canonical without full background prefetch", () => {
  assert.doesNotMatch(v22, /RECOMMENDED_PAGE_LIMIT/);
  assert.doesNotMatch(v22, /fetchCompleteRecommended/);
  assert.match(pagination, /recommended-notices/);
  assert.match(pagination, /page_size/);
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

test("recent lists keep the three-day label while the server owns the date filter", () => {
  assert.match(baseWorkspace, /مناقصات ۳ روز اخیر/);
  assert.match(baseWorkspace, /استعلامات ۳ روز اخیر/);
  assert.match(pagination, /recent_days/);
  assert.match(pagination, /publication_sort/);
});

test("recommended lists are lazy and page bounded", () => {
  assert.match(pagination, /actionable/);
  assert.match(pagination, /emptyCollectionResponse/);
  assert.match(pagination, /next:\s*null/);
  assert.match(pagination, /30 \| 50 \| 100/);
  assert.doesNotMatch(v22, /mergeUnique/);
  assert.doesNotMatch(v22, /injectedRecommendationIds/);
});
