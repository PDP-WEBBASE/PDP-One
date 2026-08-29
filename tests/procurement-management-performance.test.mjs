import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const serializers = fs.readFileSync("backend/procurement/serializers_extraction.py", "utf8");
const views = fs.readFileSync("backend/procurement/views_extraction.py", "utf8");
const dashboardView = fs.readFileSync("backend/procurement/views_dashboard_read_model.py", "utf8");

function between(text, start, end) {
  const from = text.indexOf(start);
  const to = text.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `expected bounded section ${start} -> ${end}`);
  return text.slice(from, to);
}

test("management extraction history is bounded at the authoritative server endpoint", () => {
  assert.doesNotMatch(v23, /ProcurementManagementPerformanceEnhancement/);
  assert.match(views, /class ExtractionRunPagination\(PageNumberPagination\)/);
  assert.match(views, /page_size = 20/);
  assert.match(views, /page_size_query_param = "page_size"/);
  assert.match(views, /max_page_size = 100/);
  assert.match(views, /pagination_class = ExtractionRunPagination/);
});

test("extraction list serializer omits captured page and error detail", () => {
  const listSerializer = between(serializers, "class ExtractionRunListSerializer", "class ExtractionRunSerializer");
  assert.match(listSerializer, /"summary"/);
  assert.doesNotMatch(listSerializer, /"pages"/);
  assert.doesNotMatch(listSerializer, /"errors"/);

  const detailSerializer = serializers.slice(serializers.indexOf("class ExtractionRunSerializer"));
  assert.match(detailSerializer, /"pages"/);
  assert.match(detailSerializer, /"errors"/);
});

test("extraction list avoids detail prefetch and list uses summary serializer", () => {
  assert.match(views, /if self\.action == "list":[\s\S]*return ExtractionRunListSerializer/);
  assert.match(views, /prefetch_related\([\s\S]*"connectors__source"[\s\S]*\)/);
  assert.match(views, /if self\.action == "retrieve":[\s\S]*prefetch_related\("pages__connector", "errors__connector"\)/);
});

test("dashboard performance is owned by the server read model instead of a global fetch cache", () => {
  assert.doesNotMatch(v23, /ProcurementManagementPerformanceEnhancement/);
  assert.match(dashboardView, /aggregate\(/);
  assert.match(dashboardView, /Count\(/);
});
