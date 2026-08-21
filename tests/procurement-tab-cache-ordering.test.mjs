import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const pagination = fs.readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const viewState = fs.readFileSync("app/procurement/procurementStableViewState.ts", "utf8");
const noticeView = fs.readFileSync("backend/procurement/views.py", "utf8");
const recommendedView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("tender and inquiry recent/recommended lists remain publication-date newest first", () => {
  assert.match(pagination, /-publication_sort,-last_seen_at,-id/);
  assert.match(viewState, /مناقصات ۳ روز اخیر/);
  assert.match(viewState, /استعلامات ۳ روز اخیر/);
  assert.match(pagination, /workflowCode/);
  assert.match(pagination, /COMPACT_NOTICE_PATH/);
  assert.match(noticeView, /publication_sort=Coalesce/);
  assert.match(noticeView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
  assert.match(recommendedView, /publication_sort=Coalesce/);
  assert.match(recommendedView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
});

test("loaded procurement pages are reused by the active stable list controller", () => {
  assert.match(v23, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(v23, /ProcurementTabCacheEnhancement/);
  assert.match(pagination, /__pdpStableListCache/);
  assert.match(pagination, /MAX_CACHE_ENTRIES = 60/);
  assert.match(pagination, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(pagination, /listCache\(\)\.get\(cacheKey\)/);
  assert.match(pagination, /return new Response\(JSON\.stringify\(cached\.payload\)/);
  assert.match(pagination, /pageState\.page/);
  assert.match(pagination, /pageState\.pageSize/);
});

test("real procurement mutations invalidate stable page data while navigation remains bounded", () => {
  assert.match(pagination, /method !== "GET"/);
  assert.match(pagination, /original\.pathname\.startsWith\(API_PREFIX\)\) listCache\(\)\.clear\(\)/);
  assert.match(pagination, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(pagination, /stateStillMatches/);
  assert.doesNotMatch(pagination, /fetchAll/);
  assert.doesNotMatch(pagination, /setInterval/);
});
