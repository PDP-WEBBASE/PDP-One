import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const composition = read("app/procurement/ProcurementWorkspaceV23.tsx");
const pagination = read("app/procurement/ProcurementPaginationStableEnhancement.tsx");
const compact = read("app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx");

test("V23 uses stable pagination and keeps compact DOM work client-only", () => {
  assert.match(composition, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(composition, /from "\.\/ProcurementPaginationEnhancement"/);
  assert.match(composition, /import\("\.\/ProcurementCompactWorkspaceStableEnhancement"\)/);
  assert.match(composition, /ssr:\s*false/);
  assert.doesNotMatch(composition, /import\("\.\/ProcurementCompactWorkspaceEnhancement"\)/);
});

test("pagination waits for committed tab state and drops stale metadata", () => {
  assert.match(pagination, /requestAnimationFrame/);
  assert.match(pagination, /expectedLabel/);
  assert.match(pagination, /detail\.top\s*&&\s*detail\.top\s*!==\s*top/);
  assert.match(pagination, /detail\.workflow\s*&&\s*detail\.workflow\s*!==\s*workflow/);
  assert.match(pagination, /setMeta\(null\)/);
  assert.doesNotMatch(pagination, /attributeFilter:\s*\["class"\]/);
});

test("compact UI is idempotent and no longer runs a 700ms full-DOM polling loop", () => {
  assert.match(compact, /pdpCompactSignature/);
  assert.match(compact, /new MutationObserver\(scheduleSync\)/);
  assert.match(compact, /requestAnimationFrame/);
  assert.doesNotMatch(compact, /setInterval\(syncDom\s*,\s*700\)/);
  assert.doesNotMatch(compact, /new MutationObserver\(syncDom\)/);
});

test("compact list requests stay inside the wrapper chain and preserve V13 predicates", () => {
  assert.match(compact, /innerFetch\(`\$\{COMPACT_NOTICE_PATH\}/);
  assert.doesNotMatch(compact, /nativeFetch\(`\$\{COMPACT_NOTICE_PATH\}/);
  assert.match(compact, /normalizedItem\.first_seen_at\s*=\s*`\$\{item\.published_date\}T12:00:00\+03:30`/);
  assert.match(compact, /normalizedItem\.is_recommended\s*=\s*true/);
  assert.match(compact, /__pdpCompactAbortController\?\.abort\(\)/);
});
