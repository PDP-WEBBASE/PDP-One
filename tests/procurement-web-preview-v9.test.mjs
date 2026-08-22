import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ui = readFileSync("app/procurement/ProcurementWebPreviewV9Enhancement.tsx", "utf8");
const composition = readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const pagination = readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const compactApi = readFileSync("backend/procurement/views_compact_ui.py", "utf8");
const directApi = readFileSync("backend/procurement/views_direct.py", "utf8");

test("approved V9 enhancement mounts last over the preserved stable identity layers", () => {
  assert.match(composition, /ProcurementWebPreviewV9Enhancement/);
  assert.ok(composition.indexOf("<ProcurementWebPreviewV9Enhancement />") > composition.indexOf("<ProcurementCardLayoutBulkRemoveV2 />"));
  assert.doesNotMatch(ui, /MutationObserver|setInterval\s*\(/);
});

test("V9 exposes the approved opportunity labels without title-keyword inference", () => {
  for (const label of ["مشاوره", "EPC", "احداث", "نوع فرصت"]) assert.match(ui, new RegExp(label));
  assert.match(ui, /\["consulting", "epc"\]/);
  assert.doesNotMatch(ui, /title\.includes|construction_only|recommended_for_pursuit/);
});

test("V9 multi-select filters preserve canonical source names and selected-label rules", () => {
  for (const label of ["ستاد ایران", "هزاره", "پارس‌نماد", "اهمیت", "فوریت", "وضعیت مهلت"]) assert.match(ui, new RegExp(label));
  assert.match(ui, /مورد انتخاب شده/);
  assert.match(ui, /namesAlways/);
  assert.match(pagination, /params\.append\("source_name"/);
  assert.match(pagination, /params\.append\("importance"/);
  assert.match(pagination, /params\.append\("urgency"/);
  assert.match(compactApi, /_multi_query_values/);
  assert.match(directApi, /params\.getlist\("importance"\)/);
});

test("publication filtering uses an interactive Persian calendar range and Gregorian API bounds", () => {
  assert.match(ui, /u-ca-persian/);
  assert.match(ui, /pdp-v9-calendar-panel/);
  assert.match(ui, /publishedFrom/);
  assert.match(ui, /publishedTo/);
  assert.match(pagination, /published_from/);
  assert.match(pagination, /published_to/);
  assert.match(compactApi, /published_date__gte/);
  assert.match(compactApi, /published_date__lte/);
});

test("V9 removes auxiliary counts and responsible presentation while retaining bulk controls", () => {
  assert.match(ui, /pdp-v2-row-count/);
  assert.match(ui, /pdp-v9-responsible-hidden/);
  assert.match(ui, /pdp-procurement-v9-bulk-slot/);
  assert.match(ui, /pdp-v2-selected-count/);
});
