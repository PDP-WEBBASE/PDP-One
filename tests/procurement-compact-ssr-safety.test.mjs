import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workspaceSource = fs.readFileSync(
  new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url),
  "utf8",
);

test("stable compact procurement DOM enhancement is excluded from server rendering", () => {
  assert.match(workspaceSource, /import dynamic from "next\/dynamic";/);
  assert.match(
    workspaceSource,
    /const ProcurementCompactWorkspaceStableEnhancement = dynamic\([\s\S]*?import\("\.\/ProcurementCompactWorkspaceStableEnhancement"\)[\s\S]*?\{ ssr: false \}[\s\S]*?\);/,
  );
  assert.doesNotMatch(
    workspaceSource,
    /import ProcurementCompactWorkspaceStableEnhancement from "\.\/ProcurementCompactWorkspaceStableEnhancement";/,
  );
});
