import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const procurementRoot = path.resolve("app/procurement");

// Exact known legacy debt present before the deterministic architecture migration.
// This baseline may shrink as files are migrated; any new file/rule pair fails CI.
const legacyBaseline = new Set([
  "ProcurementCardLayoutBulkRemoveV2.tsx: capture-phase global click state",
  "ProcurementCompactWorkspaceEnhancement.tsx: global fetch monkey patch",
  "ProcurementCompactWorkspaceEnhancement.tsx: capture-phase global click state",
  "ProcurementListUxRefinement.tsx: capture-phase global click state",
  "ProcurementManagementPerformanceEnhancement.tsx: global fetch monkey patch",
  "ProcurementNavigationReadCache.tsx: global fetch monkey patch",
  "ProcurementNavigationReadCache.tsx: capture-phase global click state",
  "ProcurementPaginationEnhancement.tsx: global fetch monkey patch",
  "ProcurementPaginationIntegrityEnhancement.tsx: global fetch monkey patch",
  "ProcurementPaginationStableEnhancement.tsx: global fetch monkey patch",
  "ProcurementStartupSessionResilience.tsx: global fetch monkey patch",
  "ProcurementTabCacheEnhancement.tsx: global fetch monkey patch",
  "ProcurementWorkspaceV14.tsx: global fetch monkey patch",
  "procurementStableViewState.ts: capture-phase global click state",
]);

async function sourceFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await sourceFiles(full));
    else if (/\.(?:ts|tsx)$/.test(entry.name)) files.push(full);
  }
  return files;
}

const forbidden = [
  { name: "global fetch monkey patch", pattern: /window\.fetch\s*=/ },
  { name: "window application state", pattern: /window\.__pdp[A-Za-z0-9_]*/ },
  { name: "capture-phase global click state", pattern: /document\.addEventListener\(\s*["']click["'][\s\S]{0,1200},\s*true\s*\)/ },
];

test("new procurement code cannot introduce legacy global data/state ownership", async () => {
  const detected = [];
  for (const file of await sourceFiles(procurementRoot)) {
    const relative = path.relative(procurementRoot, file);
    const source = await readFile(file, "utf8");
    for (const rule of forbidden) {
      if (!rule.pattern.test(source)) continue;
      detected.push(`${relative}: ${rule.name}`);
    }
  }

  const newViolations = detected.filter((violation) => !legacyBaseline.has(violation));
  assert.deepEqual(
    newViolations,
    [],
    `Procurement architecture drift detected:\n${newViolations.join("\n")}`,
  );
});

test("legacy architecture baseline can shrink but deterministic data client is never exempt", () => {
  assert.equal(
    [...legacyBaseline].some((entry) => entry.startsWith("procurementDataClient.ts:")),
    false,
  );
});
