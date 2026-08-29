import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");

test("V23 does not mount parallel navigation or management fetch interceptors", () => {
  assert.doesNotMatch(workspace, /ProcurementNavigationReadCache/);
  assert.doesNotMatch(workspace, /ProcurementManagementPerformanceEnhancement/);
});

test("V23 keeps a single bounded list controller during migration", () => {
  assert.match(workspace, /ProcurementPaginationStableEnhancement/);
});
