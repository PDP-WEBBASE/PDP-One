import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const procurementRoot = path.resolve("app/procurement");

const legacyAllowlist = new Set([
  "ProcurementPaginationStableEnhancement.tsx",
  "procurementStableViewState.ts",
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
  const violations = [];
  for (const file of await sourceFiles(procurementRoot)) {
    const relative = path.relative(procurementRoot, file);
    const basename = path.basename(file);
    const source = await readFile(file, "utf8");
    for (const rule of forbidden) {
      if (!rule.pattern.test(source)) continue;
      if (legacyAllowlist.has(basename)) continue;
      violations.push(`${relative}: ${rule.name}`);
    }
  }
  assert.deepEqual(violations, [], `Procurement architecture drift detected:\n${violations.join("\n")}`);
});

test("deterministic data client is not a legacy exception", () => {
  assert.equal(legacyAllowlist.has("procurementDataClient.ts"), false);
});
