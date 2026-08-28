import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appRoot = path.join(repoRoot, "app");

function sourceFiles(root) {
  const output = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) output.push(...sourceFiles(full));
    else if (/\.(?:tsx|ts|jsx|js)$/.test(entry.name)) output.push(full);
  }
  return output;
}

test("route entrypoints do not make their primary shell client-only", () => {
  const pageFiles = sourceFiles(appRoot).filter((file) => path.basename(file) === "page.tsx");
  assert.ok(pageFiles.length > 0, "expected at least one App Router page");
  for (const file of pageFiles) {
    const source = fs.readFileSync(file, "utf8");
    assert.doesNotMatch(source, /ssr\s*:\s*false/, `${path.relative(repoRoot, file)} must not make the route shell client-only`);
  }
});

test("workspace-level client-only presentation has an explicit initial-render boundary", () => {
  for (const file of sourceFiles(appRoot)) {
    const source = fs.readFileSync(file, "utf8");
    if (!/ssr\s*:\s*false/.test(source)) continue;
    const presentationOwner = /(Workspace|Shell|Page)/.test(path.basename(file));
    if (!presentationOwner) continue;
    assert.match(
      source,
      /InitialRenderBoundary/,
      `${path.relative(repoRoot, file)} uses ssr:false in a presentation owner and must provide an approved-shell initial-render boundary`,
    );
  }
});

test("procurement first paint waits for stable management shell without startup deadlock", () => {
  const workspace = fs.readFileSync(path.join(appRoot, "procurement", "ProcurementWorkspaceV23.tsx"), "utf8");
  const boundary = fs.readFileSync(path.join(appRoot, "procurement", "ProcurementInitialRenderBoundary.tsx"), "utf8");
  const management = fs.readFileSync(path.join(appRoot, "procurement", "ProcurementManagementToolsStableEnhancement.tsx"), "utf8");

  assert.match(workspace, /import ProcurementInitialRenderBoundary/);
  assert.match(workspace, /<ProcurementInitialRenderBoundary>[\s\S]*?<ProcurementWorkspaceV22 \/>[\s\S]*?<\/ProcurementInitialRenderBoundary>/);
  assert.match(boundary, /data-pdp-initial-render-ready/);
  assert.match(boundary, /\.pdp-compact-dashboard-box/);
  assert.match(boundary, /data-pdp-management-tools-stable-ready/);
  assert.match(boundary, /!finalDashboard\s*\|\|\s*!managementToolsStable/);
  assert.match(boundary, /visibility:\s*ready\s*\?\s*"visible"\s*:\s*"hidden"/);

  assert.match(management, /STABLE_READY_ATTRIBUTE\s*=\s*"data-pdp-management-tools-stable-ready"/);
  assert.match(management, /if \(!root \|\| !nav\) return false/);
  assert.match(management, /root\.setAttribute\(STABLE_READY_ATTRIBUTE,\s*"1"\)/);
  assert.match(management, /return true/);
  assert.match(management, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(management, /window\.addEventListener\(PROCUREMENT_UI_SYNC_EVENT,\s*onUiSync\)/);
  assert.match(management, /const onUiSync = \(\) => scheduleSync\(\)/);
  assert.match(management, /window\.requestAnimationFrame/);
  assert.match(management, /window\.cancelAnimationFrame\(frame1\)/);
  assert.match(management, /window\.cancelAnimationFrame\(frame2\)/);
  assert.doesNotMatch(management, /MutationObserver/);
  assert.doesNotMatch(management, /setTimeout\s*\(/);
  assert.doesNotMatch(management, /setInterval\s*\(/);

  assert.match(management, /LEGACY_FLOATING_LABELS/);
  assert.match(management, /getComputedStyle\(button\)\.position\s*===\s*"fixed"/);
  assert.match(management, /TOOLS_TAB_LABEL/);
  assert.match(management, /EXTRACTION_TAB_LABEL/);

  assert.match(boundary, /شاخص‌های مدیریتی/);
  assert.match(boundary, /ابزارهای استخراج و تحلیل/);
});
