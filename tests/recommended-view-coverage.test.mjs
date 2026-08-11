import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV22.tsx", "utf8");
const page = fs.readFileSync("app/procurement/page.tsx", "utf8");

test("procurement page activates the complete recommended coverage wrapper", () => {
  assert.match(page, /ProcurementWorkspaceV22/);
  assert.match(workspace, /ProcurementWorkspaceV21/);
});

test("recommended coverage is fetched independently from the capped recent notice list", () => {
  assert.match(workspace, /is_recommended/);
  assert.match(workspace, /RECOMMENDED_PAGE_LIMIT = 100/);
  assert.match(workspace, /rootRequestCount % 2 === 1/);
  assert.match(workspace, /fetchCompleteRecommended/);
});

test("recommended notices are de-duplicated while ordinary pagination continues", () => {
  assert.match(workspace, /mergeUnique/);
  assert.match(workspace, /injectedRecommendationIds/);
  assert.match(workspace, /isWorkspaceNoticePageRequest/);
  assert.match(workspace, /filter\(\s*\(item\) => !injectedRecommendationIds\.has/);
});
