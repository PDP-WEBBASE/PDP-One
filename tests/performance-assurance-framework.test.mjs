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


test("bounded subview attribution uses whitelisted dimensions", () => {
  const notice = read("backend/procurement/views_notice_feed_read_model.py");
  const direct = read("backend/procurement/views_direct.py");
  assert.match(notice, /NOTICE_METRIC_TYPES/);
  assert.match(notice, /NOTICE_METRIC_WORKFLOWS/);
  assert.match(notice, /procurement\.ui\.notices\.v2\.\{notice_type\}\.\{workflow\}/);
  assert.match(direct, /DIRECT_METRIC_WORKFLOWS/);
  assert.match(direct, /procurement\.ui\.direct\.list\.\{workflow\}/);
});


test("operator performance probe is bounded and explicitly gated", () => {
  const probe = read("backend/procurement/performance_probe.py");
  const core = read("backend/core/views.py");
  const mcp = read("services/pdp_mcp/server_core.py");
  assert.match(probe, /PROBE_PAGE_SIZE = 50/);
  assert.match(probe, /PROBE_CACHE_TTL_SECONDS = 60 \* 60/);
  assert.match(probe, /exact_count_used/);
  assert.match(probe, /sql_text_recorded/);
  assert.match(probe, /business_payload_recorded/);
  assert.doesNotMatch(probe, /EXPLAIN/i);
  assert.match(core, /performance_probe/);
  assert.match(core, /request\.query_params\.get\("performance_probe"/);
  assert.match(mcp, /params=\{"performance_probe": "1"\}/);
});
