import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const cache = fs.readFileSync("app/procurement/ProcurementNavigationReadCache.tsx", "utf8");
const manager = fs.readFileSync("app/procurement/FastAnalysisContextManager.tsx", "utf8");

test("general Procurement navigation cache is installed after specialized caches", () => {
  assert.match(v23, /ProcurementNavigationReadCache/);
  const tabCache = v23.indexOf("<ProcurementTabCacheEnhancement");
  const managementCache = v23.indexOf("<ProcurementManagementPerformanceEnhancement");
  const navigationCache = v23.indexOf("<ProcurementNavigationReadCache");
  assert.ok(tabCache >= 0 && managementCache > tabCache && navigationCache > managementCache);
});

test("safe Procurement JSON GETs are reused across tab remounts even when callers request no-store", () => {
  assert.match(cache, /__pdpNavigationReadCache/);
  assert.match(cache, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(cache, /DYNAMIC_CACHE_TTL_MS = 60 \* 1000/);
  assert.match(cache, /MAX_CACHE_ENTRIES = 80/);
  assert.match(cache, /MAX_ENTRY_BYTES = 2 \* 1024 \* 1024/);
  assert.match(cache, /const forceRefresh = mode === "reload" \|\| forceRefreshActive\(\)/);
  assert.match(cache, /return cachedResponse\(cached\)/);
  assert.doesNotMatch(cache, /mode !== "reload" && mode !== "no-store"/);
  assert.match(manager, /cache: "no-store"/);
});

test("specialized list caches stay authoritative for paginated high-volume pages", () => {
  assert.match(cache, /recommended-notices/);
  assert.match(cache, /direct-opportunities/);
  assert.match(cache, /extraction-runs/);
  assert.match(cache, /SPECIALIZED_LIST_PATHS\.has\(url\.pathname\)/);
});

test("writes and explicit refresh invalidate navigation data instead of serving stale values", () => {
  assert.match(cache, /MUTATING_METHODS = new Set\(\["POST", "PUT", "PATCH", "DELETE"\]\)/);
  assert.match(cache, /response\.ok && original\.pathname\.startsWith\(API_PREFIX\)[\s\S]*clearAll\(\)/);
  assert.match(cache, /REFRESH_LABEL/);
  assert.match(cache, /__pdpNavigationForceRefreshUntil/);
  assert.match(cache, /clearAllNavigationCaches\(\)/);
  assert.match(cache, /__pdpTabPageCache\?\.clear\(\)/);
  assert.match(cache, /delete guarded\.__pdpManagementDashboardCache/);
});

test("analysis activation events invalidate cached context snapshots while navigation-only events do not", () => {
  assert.match(cache, /ANALYSIS_CONTEXT_SYNC_EVENT/);
  assert.match(cache, /clearAnalysisContextEntries/);
  assert.match(cache, /detail\.source === "pagination"/);
});
