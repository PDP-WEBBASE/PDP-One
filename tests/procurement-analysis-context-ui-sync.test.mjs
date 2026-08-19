import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v14 = fs.readFileSync("app/procurement/ProcurementWorkspaceV14.tsx", "utf8");
const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const manager = fs.readFileSync("app/procurement/FastAnalysisContextManager.tsx", "utf8");
const inline = fs.readFileSync("app/procurement/ProcurementAnalysisContextInlineEnhancement.tsx", "utf8");
const sync = fs.readFileSync("app/procurement/analysisContextSync.ts", "utf8");

test("analysis settings modal is explicit and no longer hijacks section-tab clicks", () => {
  assert.doesNotMatch(v14, /labelToSection/);
  assert.doesNotMatch(v14, /document\.addEventListener\("click"/);
  assert.match(v14, /data-pdp-analysis-context-manager="true"/);
  assert.match(v14, /onClick=\{\(\) => setAnalysisSection\("prompts"\)\}/);
  assert.match(v14, /FastAnalysisContextManager/);
});

test("analysis settings render inline inside the extraction and analysis tools flow", () => {
  assert.match(v23, /ProcurementAnalysisContextInlineEnhancement/);
  assert.match(inline, /createPortal/);
  assert.match(inline, /"نقش و Prompt": "prompts"/);
  assert.match(inline, /"کلیدواژه‌ها": "keywords"/);
  assert.match(inline, /"پروفایل، صلاحیت و رزومه": "company"/);
  assert.match(inline, /"نسخه‌ها و فعال‌سازی": "versions"/);
  assert.match(inline, /data-pdp-analysis-context-inline="true"/);
});

test("active analysis content has a fast independent bootstrap and version history is deferred", () => {
  assert.match(manager, /\/analysis\/context\/active\//);
  assert.match(manager, /analysis-contexts\/\?status=draft&ordering=-version&page_size=1/);
  assert.match(manager, /section === "versions" && !versionsLoaded/);
  assert.match(manager, /analysis-contexts\/\?ordering=-version&page_size=50/);
  assert.match(manager, /analysis-contexts\/create-draft\//);
  assert.match(manager, /refreshSnapshot\(draft\.id\)/);
});

test("activation publishes a shared client sync event so open settings views update without reload", () => {
  assert.match(sync, /pdp-analysis-context-sync/);
  assert.match(manager, /emitAnalysisContextSync<ContextSnapshot>\(\{ kind: "active"/);
  assert.match(manager, /window\.addEventListener\(ANALYSIS_CONTEXT_SYNC_EVENT/);
  assert.doesNotMatch(manager, /window\.location\.reload/);
});
