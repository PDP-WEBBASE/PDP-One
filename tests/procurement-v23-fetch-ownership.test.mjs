import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const owner = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");

test("V23 mounts no browser-wide procurement fetch interceptor", () => {
  assert.doesNotMatch(workspace, /ProcurementNavigationReadCache/);
  assert.doesNotMatch(workspace, /ProcurementManagementPerformanceEnhancement/);
  assert.doesNotMatch(workspace, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(workspace, /ProcurementTabCacheEnhancement/);
});

test("React workspace owns bounded list loading and pagination", () => {
  assert.match(owner, /procurementDataClient\.staleWhileRevalidate/);
  assert.match(owner, /page:\s*noticePage/);
  assert.match(owner, /pageSize:\s*noticePageSize/);
  assert.match(owner, /<PaginationControls[\s\S]*noticePage/);
  assert.match(owner, /directController\.current\?\.abort\(\)/);
  assert.match(owner, /directGeneration\.current/);
  assert.doesNotMatch(owner, /window\.fetch\s*=/);
});
