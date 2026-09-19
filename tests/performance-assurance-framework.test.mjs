import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(path, "utf8");

test("performance assurance remains risk-based and sanitized", () => {
  const source = read("backend/procurement/performance_metrics.py");
  assert.match(source, /pdp-one\.performance-assurance\.v1/);
  assert.match(source, /hot_path/);
  assert.match(source, /measure_and_warn_by_default/);
  assert.match(source, /block_only_on_severe_material_regression/);
  assert.match(source, /sql_text_recorded/);
  assert.match(source, /business_payload_recorded/);
  assert.doesNotMatch(source, /sample\["sql"\]/);
  assert.doesNotMatch(source, /sample\["params"\]/);
});

test("performance assurance report is authenticated and read-only", () => {
  const source = read("backend/procurement/views_performance_assurance.py");
  assert.match(source, /IsAuthenticated/);
  assert.match(source, /never executes stress traffic/i);
  assert.match(source, /performance_assurance_snapshot/);
});

test("system status exposes compact assurance without changing MCP schema", () => {
  const source = read("backend/core/views.py");
  assert.match(source, /performance_assurance_snapshot\(compact=True\)/);
  assert.match(source, /"performance_assurance": performance_assurance/);
});

test("direct opportunity list participates in hot-path telemetry", () => {
  const source = read("backend/procurement/views_direct.py");
  assert.match(source, /procurement\.ui\.direct\.list/);
});
