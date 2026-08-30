import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const dataClient = fs.readFileSync("app/procurement/procurementDataClient.ts", "utf8");
const noticeView = fs.readFileSync("backend/procurement/views.py", "utf8");
const recommendedView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("tender and inquiry recent/recommended lists remain publication-date newest first", () => {
  assert.match(workspace, /-publication_sort,-last_seen_at,-id/);
  assert.match(workspace, /مناقصات اخیر/);
  assert.match(workspace, /استعلامات اخیر/);
  assert.match(workspace, /workflowCode/);
  assert.match(dataClient, /\/api\/v1\/procurement\/ui\/notices\//);
  assert.match(noticeView, /publication_sort=Coalesce/);
  assert.match(noticeView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
  assert.match(recommendedView, /publication_sort=Coalesce/);
  assert.match(recommendedView, /ordering = \["-publication_sort", "-last_seen_at", "-id"\]/);
});

test("loaded procurement pages are reused by the scoped React-owned data client", () => {
  assert.doesNotMatch(v23, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(v23, /ProcurementTabCacheEnhancement/);
  assert.match(dataClient, /private readonly cache = new Map/);
  assert.match(dataClient, /cacheTtlMs \?\? 60_000/);
  assert.match(dataClient, /procurementQueryKey\(context\)/);
  assert.match(dataClient, /getCached/);
  assert.match(dataClient, /staleWhileRevalidate/);
  assert.match(workspace, /page:\s*noticePage/);
  assert.match(workspace, /pageSize:\s*noticePageSize/);
});

test("real procurement mutations invalidate scoped page data while navigation remains bounded", () => {
  assert.match(workspace, /procurementDataClient\.invalidate/);
  assert.match(dataClient, /abortAllExcept/);
  assert.match(dataClient, /Stale procurement response discarded/);
  assert.doesNotMatch(dataClient, /window\.fetch\s*=/);
  assert.doesNotMatch(dataClient, /fetchAll/);
  assert.doesNotMatch(dataClient, /setInterval/);
});
