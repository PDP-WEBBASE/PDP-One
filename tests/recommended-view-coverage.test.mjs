import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV22.tsx", "utf8");
const baseWorkspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const page = fs.readFileSync("app/procurement/page.tsx", "utf8");
const backendView = fs.readFileSync("backend/procurement/views_recommended.py", "utf8");

test("procurement page activates the complete recommended coverage wrapper", () => {
  assert.match(page, /ProcurementWorkspaceV22/);
  assert.match(workspace, /ProcurementWorkspaceV21/);
});

test("recommended coverage comes from the canonical latest-analysis endpoint", () => {
  assert.match(workspace, /recommended-notices/);
  assert.doesNotMatch(workspace, /searchParams\.set\("is_recommended",\s*"true"\)/);
  assert.match(workspace, /RECOMMENDED_PAGE_LIMIT = 100/);
  assert.match(workspace, /fetchCompleteRecommended/);
  assert.match(backendView, /latest_effective_recommendation/);
  assert.match(backendView, /NoticeAnalysisDraft/);
  assert.match(backendView, /review_status=NoticeAnalysisDraft\.ReviewStatus\.REJECTED/);
  assert.match(backendView, /filter\(ai_is_recommended=True\)/);
});

test("general tender and inquiry view is recent while recommendations keep full history", () => {
  assert.match(baseWorkspace, /RECENT_NOTICE_DAYS = 3/);
  assert.match(baseWorkspace, /view === "all"\) return isRecentNotice\(item\.first_seen_at\)/);
  assert.match(baseWorkspace, /view === "recommended"\) return item\.is_recommended;/);
  assert.match(baseWorkspace, /مناقصات ۳ روز اخیر/);
  assert.match(baseWorkspace, /استعلامات ۳ روز اخیر/);
});

test("recommended notices are de-duplicated while ordinary pagination continues", () => {
  assert.match(workspace, /mergeUnique/);
  assert.match(workspace, /injectedRecommendationIds/);
  assert.match(workspace, /isWorkspaceNoticePageRequest/);
  assert.match(workspace, /filter\(\s*\(item\) => !injectedRecommendationIds\.has/);
});
