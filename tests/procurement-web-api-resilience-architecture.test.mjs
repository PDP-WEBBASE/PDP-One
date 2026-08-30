import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("active Procurement composition has no browser-wide fetch replacement", async () => {
  const [v14, startup, v23] = await Promise.all([
    read("app/procurement/ProcurementWorkspaceV14.tsx"),
    read("app/procurement/ProcurementStartupSessionResilience.tsx"),
    read("app/procurement/ProcurementWorkspaceV23.tsx"),
  ]);
  assert.doesNotMatch(v14, /window\.fetch\s*=/);
  assert.doesNotMatch(startup, /window\.fetch\s*=/);
  assert.doesNotMatch(v14, /10_000|FETCH_RECOVERY_ATTEMPTS|probeFailedEndpoint/);
  assert.match(v23, /ProcurementStartupSessionResilience/);
});

test("compact presentation layer does not own Dashboard or Sources reads", async () => {
  const compact = await read("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx");
  assert.doesNotMatch(compact, /ui\/dashboard/);
  assert.doesNotMatch(compact, /fetch\(`\$\{PROCUREMENT_API\}\/sources\//);
  assert.match(compact, /enhanceRecordCards/);
  assert.match(compact, /bulkDismiss/);
});

test("notice hot path uses bounded look-ahead rather than exact count", async () => {
  const view = await read("backend/procurement/views_notice_feed_read_model.py");
  const urls = await read("backend/procurement/urls.py");
  assert.match(view, /page_size \+ 1/);
  assert.match(view, /has_more/);
  assert.match(view, /count_is_exact/);
  assert.doesNotMatch(view, /queryset\.count\(\)/);
  assert.match(urls, /path\("ui\/notices\/", bounded_notice_feed/);
});

test("Dashboard V2 avoids the historical full analysis statistics hot path", async () => {
  const dashboard = await read("backend/procurement/views_dashboard_read_model.py");
  assert.doesNotMatch(dashboard, /procurement_analysis_statistics/);
  assert.match(dashboard, /DASHBOARD_CACHE_TTL_SECONDS = 20/);
  assert.match(dashboard, /persisted_run_counters_or_bounded_split/);
  assert.match(dashboard, /aggregate\(/);
});

test("request governor is bounded single-flight and circuit protected", async () => {
  const client = await read("app/procurement/procurementRequestClient.ts");
  assert.match(client, /DEFAULT_CONCURRENCY = 3/);
  assert.match(client, /private readonly inflight = new Map/);
  assert.match(client, /CIRCUIT_FAILURE_THRESHOLD = 3/);
  assert.match(client, /CIRCUIT_OPEN_MS = 30_000/);
  assert.match(client, /maxAttempts = options\.retryTransient === false \? 1 : 2/);
  assert.doesNotMatch(client, /window\.fetch\s*=/);
});

test("management failures are degraded state, never silent empty-state replacement", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV13.tsx");
  assert.match(workspace, /Promise\.allSettled/);
  assert.match(workspace, /if \(sourceResult\.status === "fulfilled"\) setSources\(sourceResult\.value\); else failures \+= 1/);
  assert.match(workspace, /if \(runResult\.status === "fulfilled"\) setExtractionRuns\(runResult\.value\); else failures \+= 1/);
  assert.match(workspace, /بخشی از اطلاعات مدیریت زیرسامانه موقتاً بارگذاری نشد/);
  assert.doesNotMatch(workspace, /else\s+setSources\(\[\]\)/);
  assert.doesNotMatch(workspace, /else\s+setExtractionRuns\(\[\]\)/);
});

test("revision sync has one visible-view owner and invalidates scoped read caches", async () => {
  const [workspace, compact, v14, startup] = await Promise.all([
    read("app/procurement/ProcurementWorkspaceV13.tsx"),
    read("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx"),
    read("app/procurement/ProcurementWorkspaceV14.tsx"),
    read("app/procurement/ProcurementStartupSessionResilience.tsx"),
  ]);
  const revisionCalls = workspace.match(/interaction\/revision\//g) || [];
  assert.equal(revisionCalls.length, 1);
  assert.match(workspace, /document\.visibilityState !== "visible"/);
  assert.match(workspace, /procurementDataClient\.invalidate\(\)/);
  assert.match(workspace, /directCache\.current\.clear\(\)/);
  assert.doesNotMatch(compact, /interaction\/revision\//);
  assert.doesNotMatch(v14, /interaction\/revision\//);
  assert.doesNotMatch(startup, /interaction\/revision\//);
});
