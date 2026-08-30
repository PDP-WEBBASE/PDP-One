import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const semantics = readFileSync("app/procurement/directWorkflowSemantics.ts", "utf8");
const directApi = readFileSync("backend/procurement/views_direct.py", "utf8");

test("direct recent entry has an explicit unfiltered API projection", () => {
  assert.match(semantics, /return view === \"all\" \? \"\" : view/);
  assert.doesNotMatch(semantics, /return view === \"all\" \? \"recommended\" : view/);
});

test("backend keeps recommended as an explicit optional workflow instead of default list semantics", () => {
  assert.match(directApi, /if workflow_view == \"recommended\":/);
  assert.match(directApi, /queryset = queryset\.filter\(stage__in=DIRECT_RECOMMENDED_STAGES\)/);
});
