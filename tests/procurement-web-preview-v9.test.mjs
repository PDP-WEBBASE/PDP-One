import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ui = readFileSync("app/procurement/ProcurementWebPreviewV9Enhancement.tsx", "utf8");
const composition = readFileSync("app/procurement/ProcurementWorkspaceV23.tsx", "utf8");
const workspace = readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");
const pagination = readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const compactApi = readFileSync("backend/procurement/views_compact_ui.py", "utf8");
const directApi = readFileSync("backend/procurement/views_direct.py", "utf8");

test("approved V9 enhancement mounts last over the preserved stable identity layers", () => {
  assert.match(composition, /ProcurementWebPreviewV9Enhancement/);
  assert.ok(composition.indexOf("<ProcurementWebPreviewV9Enhancement />") > composition.indexOf("<ProcurementCardLayoutBulkRemoveV2 />"));
  assert.match(composition, /import\("\.\/ProcurementWebPreviewV9Enhancement"\)[\s\S]*?ssr:\s*false/);
  assert.doesNotMatch(ui, /MutationObserver|setInterval\s*\(/);
});

test("V9 controls are native React children and cannot be detached by an async workspace render", () => {
  assert.match(workspace, /import[\s\S]*ProcurementV9NativeFilters[\s\S]*ProcurementV9NativeToolbar[\s\S]*from "\.\/ProcurementWebPreviewV9Enhancement"/);
  assert.match(workspace, /pdp-v9-workflow-row[\s\S]*<ProcurementV9NativeToolbar\s*\/>/);
  assert.match(workspace, /pdp-v9-filter-bar[\s\S]*<ProcurementV9NativeFilters noticeTab\s*\/>/);
  assert.match(workspace, /tab === "direct"[\s\S]*ProcurementV9NativeToolbar[\s\S]*ProcurementV9NativeFilters noticeTab=\{false\}/);
  assert.match(workspace, /function clearVisibleFilters\(\)[\s\S]*resetProcurementV9NativeFilters\(\)/);
  assert.doesNotMatch(ui, /createPortal|document\.createElement|ensureHosts|FILTER_HOST_ID|TOOLBAR_HOST_ID/);
  assert.match(ui, /window\.addEventListener\(NOTICE_DATA_EVENT, schedule\)/);
  assert.match(ui, /window\.addEventListener\(DIRECT_DATA_EVENT, schedule\)/);
  assert.match(ui, /align-items:flex-end!important;justify-content:space-between!important;gap:14px!important/);
});

test("V9 uses the approved exact filter and badge geometry instead of the earlier overlay dimensions", () => {
  assert.match(ui, /grid-template-columns:minmax\(230px,1\.55fr\) repeat\(5,minmax\(108px,\.72fr\)\) minmax\(225px,1\.18fr\) auto!important/);
  assert.match(ui, /min-height:34px!important;padding:5px 7px!important;font-size:11\.5px!important/);
  assert.match(ui, /min-height:22px!important;padding:2px 8px!important;border-radius:999px!important/);
  for (const tone of ["neutral", "danger", "high", "medium", "safe"]) assert.match(ui, new RegExp(`pdp-v9-${tone}`));
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
  assert.match(pagination, /params\.append\("business_opportunity_type"/);
  assert.match(compactApi, /business_opportunity_type__in/);
  assert.match(directApi, /business_opportunity_type__in/);
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
