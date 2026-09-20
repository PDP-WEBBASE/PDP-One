import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("bounded predictive prefetch is first-page only with hard concurrency cap two", async () => {
  const client = await read("app/procurement/procurementDataClient.ts");
  assert.match(client, /prefetchConcurrency = Math\.min\(2, Math\.max\(1,/);
  assert.match(client, /procurement-prefetch-first-page-only/);
  assert.match(client, /context\.page\) !== 1/);
  assert.match(client, /prefetchActive < this\.prefetchConcurrency/);
  assert.match(client, /prefetchQueue/);
  assert.match(client, /abortAllExcept/);
  assert.match(client, /cancelQueuedPrefetch/);
});

test("prefetch uses the canonical ProcurementDataClient cache and never patches global fetch", async () => {
  const client = await read("app/procurement/procurementDataClient.ts");
  assert.match(client, /this\.prefetchedKeys\.add\(key\)/);
  assert.match(client, /this\.cache\.set\(key/);
  assert.match(client, /const existing = this\.inflight\.get\(key\)/);
  assert.doesNotMatch(client, /window\.fetch\s*=/);
});

test("Procurement warms only bounded page-one notice views after usable data and browser idle", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV13.tsx");
  assert.match(workspace, /NOTICE_PREFETCH_WORKFLOWS/);
  assert.match(workspace, /scheduleBrowserIdle/);
  assert.match(workspace, /context\.page === 1 && noNoticeFiltersActive\(context\)/);
  assert.match(workspace, /workflow: "recent"/);
  assert.match(workspace, /Promise\.allSettled\(siblings\.map\(\(candidate\) => procurementDataClient\.prefetch\(candidate\)\)\)/);
  assert.doesNotMatch(workspace, /pagination-metadata\/\?[^\n]*prefetch/i);
});

test("revision changes use affected contexts before any broad reconciliation fallback", async () => {
  const [workspace, client] = await Promise.all([
    read("app/procurement/ProcurementWorkspaceV13.tsx"),
    read("app/procurement/procurementDataClient.ts"),
  ]);
  assert.match(workspace, /interaction\/changes\/\?since=\$\{fromRevision\}&limit=500/);
  assert.match(workspace, /affected_contexts/);
  assert.match(workspace, /invalidateAffectedContexts\(affectedContexts\)/);
  assert.match(workspace, /broadReconciliationRefresh/);
  assert.match(client, /invalidateAffectedContexts/);
  assert.match(client, /dashboardAffected/);
  assert.match(client, /directAffected/);
});

test("browser-path timing distinguishes cold, cache and prefetch hit without business payloads", async () => {
  const [workspace, client] = await Promise.all([
    read("app/procurement/ProcurementWorkspaceV13.tsx"),
    read("app/procurement/procurementDataClient.ts"),
  ]);
  assert.match(client, /PROCUREMENT_BROWSER_PERFORMANCE_EVENT/);
  assert.match(client, /"cold-network" \| "cache-hit" \| "prefetch-hit"/);
  assert.match(workspace, /clickToUsableMs/);
  assert.match(workspace, /requestAnimationFrame/);
  assert.match(workspace, /cacheOrigin === "prefetch"/);
  assert.doesNotMatch(client, /title.*ProcurementBrowserPerformanceDetail/);
  assert.doesNotMatch(client, /noticeId.*ProcurementBrowserPerformanceDetail/);
});

test("empty filter arrays canonicalize to the same cache context as no filters", async () => {
  const client = await read("app/procurement/procurementDataClient.ts");
  assert.match(client, /!Array\.isArray\(value\) \|\| value\.length > 0/);
  assert.match(client, /normalizedFilterEntries\(context\.filters\)/);
});
