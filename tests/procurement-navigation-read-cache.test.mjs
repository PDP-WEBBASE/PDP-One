import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const stableList = fs.readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const dataClient = fs.readFileSync("app/procurement/procurementDataClient.ts", "utf8");
const manager = fs.readFileSync("app/procurement/FastAnalysisContextManager.tsx", "utf8");

test("V23 no longer installs a general global fetch cache", () => {
  assert.doesNotMatch(v23, /ProcurementNavigationReadCache/);
  assert.doesNotMatch(v23, /ProcurementManagementPerformanceEnhancement/);
  assert.match(v23, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(v23, /ProcurementTabCacheEnhancement/);
});

test("visited high-volume list pages remain bounded and reusable during migration", () => {
  assert.match(stableList, /CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(stableList, /MAX_CACHE_ENTRIES = 60/);
  assert.match(stableList, /readCache\(\)/);
  assert.match(stableList, /cached\.payload/);
  assert.match(stableList, /stateStillMatches/);
});

test("new scoped data client owns context cache and stale-while-revalidate without window globals", () => {
  assert.match(dataClient, /private readonly cache = new Map/);
  assert.match(dataClient, /staleWhileRevalidate/);
  assert.match(dataClient, /prefetch/);
  assert.match(dataClient, /AbortController/);
  assert.match(dataClient, /requestGeneration/);
  assert.doesNotMatch(dataClient, /window\.fetch\s*=/);
  assert.doesNotMatch(dataClient, /window\.__pdp/);
});

test("current no-store analysis callers remain explicit rather than relying on a global cache override", () => {
  assert.match(manager, /cache: "no-store"/);
  assert.doesNotMatch(v23, /ProcurementNavigationReadCache/);
});

test("writes are not hidden behind a browser-wide read cache", () => {
  assert.doesNotMatch(v23, /ProcurementNavigationReadCache/);
  assert.match(dataClient, /invalidate\(/);
});
