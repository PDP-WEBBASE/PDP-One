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

test("procurement first paint hides the legacy workspace until the approved dashboard is ready", () => {
  const workspace = fs.readFileSync(path.join(appRoot, "procurement", "ProcurementWorkspaceV23.tsx"), "utf8");
  const boundary = fs.readFileSync(path.join(appRoot, "procurement", "ProcurementInitialRenderBoundary.tsx"), "utf8");

  assert.match(workspace, /import ProcurementInitialRenderBoundary/);
  assert.match(workspace, /<ProcurementInitialRenderBoundary>[\s\S]*?<ProcurementWorkspaceV22 \/>[\s\S]*?<\/ProcurementInitialRenderBoundary>/);
  assert.match(boundary, /data-pdp-initial-render-ready/);
  assert.match(boundary, /\.pdp-compact-dashboard-box/);
  assert.match(boundary, /visibility:\s*ready\s*\?\s*"visible"\s*:\s*"hidden"/);
  assert.match(boundary, /new MutationObserver/);
  assert.match(boundary, /observer\.observe\(root,/);
  assert.doesNotMatch(boundary, /observer\.observe\(document\.body/);
  assert.match(boundary, /شاخص‌های مدیریتی/);
  assert.match(boundary, /ابزارهای استخراج و تحلیل/);
});
