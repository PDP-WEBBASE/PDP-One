import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const cache = fs.readFileSync("app/procurement/ProcurementNavigationReadCache.tsx", "utf8");
const pagination = fs.readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const manager = fs.readFileSync("app/procurement/FastAnalysisContextManager.tsx", "utf8");

test("general Procurement navigation cache is installed after the single specialized list controller", () => {
  assert.match(v23, /ProcurementNavigationReadCache/);
  const paginationController = v23.indexOf("<ProcurementPaginationStableEnhancement");
  const managementCache = v23.indexOf("<ProcurementManagementPerformanceEnhancement");
  const navigationCache = v23.indexOf("<ProcurementNavigationReadCache");
  assert.ok(paginationController >= 0 && managementCache > paginationController && navigationCache > managementCache);
  assert.doesNotMatch(v23, /ProcurementTabCacheEnhancement/);
});

test("visited non-list Procurement JSON stays immediately available and stale reads revalidate in background", () => {
  assert.match(cache, /__pdpNavigationReadCache/);
  assert.match(cache, /__pdpNavigationReadRevalidating/);
  assert.match(cache, /CACHE_REVALIDATE_MS = 5 \* 60 \* 1000/);
  assert.match(cache, /DYNAMIC_REVALIDATE_MS = 60 \* 1000/);
  assert.match(cache, /MAX_CACHE_ENTRIES = 80/);
  assert.match(cache, /MAX_ENTRY_BYTES = 2 \* 1024 \* 1024/);
  assert.match(cache, /revalidateInBackground\(key, input, init, previousFetch\)/);
  assert.match(cache, /return cachedResponse\(cached\)/);
  assert.match(cache, /Date\.now\(\) - cached\.storedAt > revalidateAfter\(original\.pathname\)/);
  assert.doesNotMatch(cache, /if \(cached\) readCache\(\)\.delete\(key\)/);
});

test("current no-store analysis callers can still reuse the navigation-session copy", () => {
  assert.match(manager, /cache: "no-store"/);
  assert.match(cache, /const forceRefresh = mode === "reload" \|\| forceRefreshActive\(\)/);
  assert.doesNotMatch(cache, /mode !== "reload" && mode !== "no-store"/);
});

test("high-volume list caching is owned only by stable pagination and excluded from general cache", () => {
  assert.match(cache, /recommended-notices/);
  assert.match(cache, /direct-opportunities/);
  assert.match(cache, /SPECIALIZED_LIST_PATHS\.has\(url\.pathname\)/);
  assert.match(pagination, /__pdpStableListCache/);
  assert.match(pagination, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.doesNotMatch(pagination, /MutationObserver/);
  assert.doesNotMatch(pagination, /setInterval/);
});

test("writes and explicit refresh invalidate navigation data instead of serving stale values", () => {
  assert.match(cache, /MUTATING_METHODS = new Set\(\["POST", "PUT", "PATCH", "DELETE"\]\)/);
  assert.match(cache, /response\.ok && original\.pathname\.startsWith\(API_PREFIX\)[\s\S]*clearAll\(\)/);
  assert.match(cache, /REFRESH_LABEL/);
  assert.match(cache, /__pdpNavigationForceRefreshUntil/);
  assert.match(cache, /clearAllNavigationCaches\(\)/);
  assert.match(pagination, /method !== "GET"[\s\S]*listCache\(\)\.clear\(\)/);
});

test("analysis activation events invalidate cached context snapshots while navigation-only events do not", () => {
  assert.match(cache, /ANALYSIS_CONTEXT_SYNC_EVENT/);
  assert.match(cache, /clearAnalysisContextEntries/);
  assert.match(cache, /detail\.source === "pagination"/);
});
