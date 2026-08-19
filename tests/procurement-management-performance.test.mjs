import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v23 = fs.readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const management = fs.readFileSync("app/procurement/ProcurementManagementPerformanceEnhancement.tsx", "utf8");
const serializers = fs.readFileSync("backend/procurement/serializers_extraction.py", "utf8");
const views = fs.readFileSync("backend/procurement/views_extraction.py", "utf8");

function between(text, start, end) {
  const from = text.indexOf(start);
  const to = text.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `expected bounded section ${start} -> ${end}`);
  return text.slice(from, to);
}

test("management extraction history is bounded to one recent UI page", () => {
  assert.match(v23, /ProcurementManagementPerformanceEnhancement/);
  assert.match(management, /MANAGEMENT_HISTORY_PAGE_SIZE = 20/);
  assert.match(management, /original\.pathname === EXTRACTION_RUNS_PATH/);
  assert.match(management, /searchParams\.set\("page", "1"\)/);
  assert.match(management, /searchParams\.set\("page_size", String\(MANAGEMENT_HISTORY_PAGE_SIZE\)\)/);
  assert.match(management, /\{ \.\.\.payload, next: null, previous: null \}/);
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

test("report dashboard result is briefly reused and invalidated after real mutations", () => {
  assert.match(management, /DASHBOARD_CACHE_TTL_MS = 60 \* 1000/);
  assert.match(management, /__pdpManagementDashboardCache/);
  assert.match(management, /original\.pathname === DASHBOARD_PATH/);
  assert.match(management, /PROCUREMENT_UI_SYNC_EVENT/);
  assert.match(management, /detail\.source === "pagination"/);
  assert.match(management, /delete \(window as ManagementWindow\)\.__pdpManagementDashboardCache/);
});
