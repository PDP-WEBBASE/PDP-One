import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const composition = read("app/procurement/ProcurementWorkspaceV23.tsx");
const ux = read("app/procurement/ProcurementListUxRefinement.tsx");
const base = read("app/procurement/ProcurementWorkspaceV13.tsx");
const pagination = read("app/procurement/ProcurementPaginationStableEnhancement.tsx");

test("refinement mounts last without replacing stable pagination or SSR boundaries", () => {
  assert.match(composition, /ProcurementPaginationStableEnhancement/);
  assert.match(composition, /ProcurementCompactWorkspaceStableEnhancement/);
  assert.match(composition, /ssr:\s*false/);
  assert.match(composition, /ProcurementListUxRefinement/);
  assert.ok(composition.indexOf("<ProcurementListUxRefinement />") > composition.indexOf("<ProcurementFullTitleEnhancement />"));
  assert.doesNotMatch(ux, /MutationObserver/);
  assert.doesNotMatch(ux, /setInterval/);
  assert.doesNotMatch(ux, /window\.fetch\s*=/);
});

test("all legacy procurement filters remain present and added filters stay bounded", () => {
  for (const label of ["جست‌وجو", "منبع", "استان", "اهمیت", "فوریت", "پاک‌کردن"]) assert.match(base, new RegExp(label));
  assert.match(ux, /وضعیت مهلت/);
  assert.match(ux, /تاریخ انتشار/);
  assert.match(ux, /پdp|pdp/);
  assert.match(pagination, /deadline_status/);
  assert.match(pagination, /published_on/);
  assert.match(ux, /setAddedFilterGlobals\("", ""\)/);
});

test("publication date is presented as Jalali while API keeps Gregorian published_on", () => {
  assert.match(ux, /fa-IR|u-ca-persian/);
  assert.match(ux, /gregorianToJalali/);
  assert.match(ux, /jalaliToGregorian/);
  assert.match(ux, /۱۴۰۵\/۰۵\/۲۹/);
  assert.match(ux, /pdp-ux-native-date/);
  assert.match(pagination, /params\.set\("published_on", filters\.publishedOn\)/);
});

test("source links use requested Setad-Hezareh-ParsNamad order and duplicate source/facts are suppressed", () => {
  assert.match(ux, /token\.includes\("setad"\).*return 0/s);
  assert.match(ux, /token\.includes\("hezareh"\).*return 1/s);
  assert.match(ux, /token\.includes\("parsnamad"\).*return 2/s);
  assert.match(ux, /direction:ltr/);
  assert.match(ux, /pdp-ux-native-source/);
  assert.match(ux, /pdp-ux-duplicate-fact/);
  assert.match(ux, /باقی‌مانده/);
});

test("recommended rows support explicit page selection and bounded selected-id bulk dismissal", () => {
  assert.match(ux, /انتخاب همه این صفحه/);
  assert.match(ux, /حذف گروهی از پیشنهادی/);
  assert.match(ux, /notice_ids: ids/);
  assert.match(ux, /dismiss-bulk/);
  assert.doesNotMatch(ux, /dismiss_all:\s*true/);
  assert.match(ux, /ROW_SELECT_EVENT/);
});

test("titles get substantially more room before two-line truncation", () => {
  assert.match(ux, /title\.length > 320/);
  assert.match(ux, /remove\("pdp-full-title-long"\)/);
  assert.match(ux, /pdp-ux-title-long/);
  assert.match(ux, /-webkit-line-clamp:2/);
});

test("direct workflow hides recommended subtab and restores current-list selection", () => {
  assert.match(ux, /suppressDirectRecommendedTab/);
  assert.match(ux, /normalize\(button\.textContent\) === "پیشنهادی"/);
  assert.match(ux, /state\.workflow === "all"/);
  assert.match(ux, /SELECTABLE_DIRECT_STAGES/);
  assert.match(ux, /body: JSON\.stringify\(\{ stage: "selected" \}\)/);
});

test("management tools injected tab owns active visual state while open", () => {
  assert.match(ux, /data-pdp-management-tools-tab/);
  assert.match(ux, /ابزارهای استخراج و تحلیل/);
  assert.match(ux, /toolsButton\.style\.background = toolsActive \? "#145563"/);
  assert.match(ux, /aria-selected/);
});
