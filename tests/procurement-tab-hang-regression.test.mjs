import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const composition = read("app/procurement/ProcurementWorkspaceV23.tsx");
const pagination = read("app/procurement/ProcurementPaginationStableEnhancement.tsx");
const compact = read("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx");
const viewState = read("app/procurement/procurementStableViewState.ts");
const fullTitle = read("app/procurement/ProcurementFullTitleEnhancement.tsx");

test("V23 keeps one bounded list controller and removes legacy competing DOM/cache layers", () => {
  assert.match(composition, /ProcurementPaginationStableEnhancement/);
  assert.match(composition, /import\("\.\/ProcurementCompactWorkspaceStableEnhancement"\)/);
  assert.match(composition, /ssr:\s*false/);
  assert.doesNotMatch(composition, /ProcurementTabCacheEnhancement/);
  assert.doesNotMatch(composition, /ProcurementPaginationIntegrityEnhancement/);
  assert.doesNotMatch(composition, /ProcurementPaginationEnhancement/);
});

test("top and workflow state comes from captured user intent, never class-name guessing", () => {
  assert.match(viewState, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(viewState, /document\.addEventListener\("click"/);
  assert.match(viewState, /TOP_BY_LABEL/);
  assert.match(viewState, /WORKFLOW_BY_LABEL/);
  assert.doesNotMatch(viewState, /className/);
  assert.doesNotMatch(viewState, /MutationObserver/);

  assert.match(pagination, /getProcurementStableViewState/);
  assert.match(compact, /getProcurementStableViewState/);
  assert.doesNotMatch(pagination, /Boolean\(normalize\([^\n]*class/);
  assert.doesNotMatch(compact, /Boolean\(normalize\([^\n]*class/);
});

test("list loading is page-bounded, cached, and stale responses are context-checked", () => {
  assert.match(pagination, /type PageSize = 30 \| 50 \| 100/);
  assert.match(pagination, /page_size/);
  assert.match(pagination, /CACHE_TTL_MS/);
  assert.match(pagination, /stateStillMatches/);
  assert.match(pagination, /next: null/);
  assert.match(pagination, /requestAnimationFrame\(emitRefresh\)/);
  assert.doesNotMatch(pagination, /MutationObserver/);
  assert.doesNotMatch(pagination, /setInterval/);
});

test("compact and title presentation are event-driven without DOM observation loops", () => {
  assert.match(compact, /pdpCompactSignature/);
  assert.match(compact, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(compact, /pdp-procurement-compact-notice-data/);
  assert.match(compact, /requestAnimationFrame/);
  assert.doesNotMatch(compact, /MutationObserver/);
  assert.doesNotMatch(compact, /setInterval/);
  assert.doesNotMatch(compact, /window\.fetch\s*=/);

  assert.match(fullTitle, /PROCUREMENT_STABLE_VIEW_STATE_EVENT/);
  assert.match(fullTitle, /requestAnimationFrame/);
  assert.doesNotMatch(fullTitle, /MutationObserver/);
});

test("compact server feed preserves V13 recent/recommended predicates", () => {
  assert.match(pagination, /normalizedItem\.first_seen_at\s*=\s*`\$\{publishedDate\}T12:00:00\+03:30`/);
  assert.match(pagination, /normalizedItem\.is_recommended\s*=\s*true/);
  assert.match(pagination, /COMPACT_NOTICE_PATH/);
});
