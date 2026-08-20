import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../app/procurement/ProcurementFullTitleEnhancement.tsx", import.meta.url), "utf8");
const workspace = fs.readFileSync(new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url), "utf8");

test("full-title enhancement is mounted after compact row enhancement", () => {
  assert.match(workspace, /ProcurementFullTitleEnhancement/);
  assert.ok(workspace.indexOf("<ProcurementFullTitleEnhancement />") > workspace.indexOf("<ProcurementCompactWorkspaceEnhancement />"));
});

test("normal procurement titles explicitly reset inherited ellipsis", () => {
  assert.match(source, /white-space:normal!important/);
  assert.match(source, /overflow:visible!important/);
  assert.match(source, /text-overflow:clip!important/);
  assert.match(source, /LONG_TITLE_THRESHOLD = 220/);
});

test("only genuinely long titles receive a bounded two-line clamp", () => {
  assert.match(source, /pdp-full-title-long/);
  assert.match(source, /length > LONG_TITLE_THRESHOLD/);
  assert.match(source, /-webkit-line-clamp:2!important/);
});

test("title behavior applies to tenders, inquiries and direct referrals", () => {
  assert.match(source, /مناقصات/);
  assert.match(source, /استعلامات/);
  assert.match(source, /ارجاعات مستقیم/);
});
