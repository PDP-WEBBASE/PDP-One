import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const pagination = fs.readFileSync("app/procurement/ProcurementPaginationEnhancement.tsx", "utf8");
const cache = fs.readFileSync("app/procurement/ProcurementTabCacheEnhancement.tsx", "utf8");
const noticeView = fs.readFileSync("backend/procurement/views.py", "utf8");
const recommendedView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("tender and inquiry recent/recommended lists are publication-date newest first", () => {
  assert.match(pagination, /ordering", "-publication_sort,-last_seen_at,-id"/);
  assert.match(pagination, /مناقصات ۳ روز اخیر/);
  assert.match(pagination, /استعلامات ۳ روز اخیر/);
  assert.match(pagination, /recent_days", "3"/);
  assert.match(pagination, /actionable", "true"/);
  assert.match(noticeView, /publication_sort=Coalesce/);
  assert.match(noticeView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
  assert.match(recommendedView, /publication_sort=Coalesce/);
  assert.match(recommendedView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
});

test("loaded procurement pages are reused when revisiting the same tab context", () => {
  assert.match(v23, /ProcurementTabCacheEnhancement/);
  assert.match(cache, /__pdpTabPageCache/);
  assert.match(cache, /MAX_CACHE_ENTRIES = 60/);
  assert.match(cache, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(cache, /cache\.get\(context\.key\)/);
  assert.match(cache, /return cachedResponse\(cached\)/);
  assert.match(cache, /state\.page, state\.pageSize/);
});

test("navigation preserves cache while real procurement mutations invalidate affected data", () => {
  assert.match(cache, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(cache, /detail\.source === "pagination"/);
  assert.match(cache, /detail\.bulkWorkspace[\s\S]*pageCache\(\)\.clear\(\)/);
  assert.match(cache, /detail\.noticeId[\s\S]*clearKind\("notice"\)/);
  assert.match(cache, /detail\.directId[\s\S]*clearKind\("direct"\)/);
});
