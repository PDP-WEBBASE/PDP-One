import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const directApi = readFileSync("backend/procurement/views_direct.py", "utf8");

test("direct recent entry is not contractually equivalent to recommended", () => {
  // R5 requires the user-facing recent entry to remain distinct from the suggested/recommended stage filter.
  assert.doesNotMatch(workspace, /function directWorkflowCode\(view: WorkflowView\) \{\s*return view === \"all\" \? \"recommended\" : view;/);
});

test("backend keeps recommended as an explicit optional workflow instead of default list semantics", () => {
  assert.match(directApi, /if workflow_view == \"recommended\":/);
  assert.match(directApi, /queryset = queryset\.filter\(stage__in=DIRECT_RECOMMENDED_STAGES\)/);
});
