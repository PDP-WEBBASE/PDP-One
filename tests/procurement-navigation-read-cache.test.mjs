import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const dataClient = fs.readFileSync("app/procurement/procurementDataClient.ts", "utf8");
const manager = fs.readFileSync("app/procurement/FastAnalysisContextManager.tsx", "utf8");

test("active Procurement runtime has no global fetch cache or interceptor", () => {
  assert.doesNotMatch(v23, /ProcurementNavigationReadCache/);
  assert.doesNotMatch(v23, /ProcurementManagementPerformanceEnhancement/);
  assert.doesNotMatch(v23, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(v23, /ProcurementTabCacheEnhancement/);
  assert.doesNotMatch(workspace, /window\.fetch\s*=/);
});

test("scoped data client owns context cache, SWR, dedupe, abort and stale protection", () => {
  assert.match(dataClient, /private readonly cache = new Map/);
  assert.match(dataClient, /private readonly inflight = new Map/);
  assert.match(dataClient, /staleWhileRevalidate/);
  assert.match(dataClient, /prefetch/);
  assert.match(dataClient, /AbortController/);
  assert.match(dataClient, /requestGeneration/);
  assert.match(dataClient, /Stale procurement response discarded/);
  assert.doesNotMatch(dataClient, /window\.fetch\s*=/);
  assert.doesNotMatch(dataClient, /window\.__pdp/);
});

test("workspace uses lazy view-scoped list requests instead of initial list hydration", () => {
  assert.match(workspace, /tab !== "dashboard"/);
  assert.match(workspace, /tab !== "tenders" && tab !== "inquiries"/);
  assert.match(workspace, /tab !== "direct"/);
  assert.match(workspace, /ui\/dashboard\//);
  assert.doesNotMatch(workspace, /Promise\.all\(\[\s*fetchCollection<ApiNotice>/);
  assert.doesNotMatch(workspace, /fetchCollection<ApiNotice>\(`\$\{PROCUREMENT_API\}\/notices\/\?ordering=-last_seen_at`\)/);
});

test("writes explicitly invalidate scoped caches", () => {
  assert.match(workspace, /procurementDataClient\.invalidate\(\)/);
  assert.match(workspace, /directCache\.current\.clear\(\)/);
  assert.match(dataClient, /invalidate\(/);
});

test("current no-store analysis callers remain explicit", () => {
  assert.match(manager, /cache: "no-store"/);
});
