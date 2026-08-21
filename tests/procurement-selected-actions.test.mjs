import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const actionsPath = new URL("../app/procurement/ProcurementWorkflowActionsStableEnhancement.tsx", import.meta.url);
const toolsPath = new URL("../app/procurement/ProcurementManagementToolsStableEnhancement.tsx", import.meta.url);
const metadataPath = new URL("../backend/procurement/views_workflow_ui.py", import.meta.url);

test("organizes management tools without a body-wide DOM watcher and preserves internet monitoring", async () => {
  const source = await readFile(toolsPath, "utf8");
  assert.match(source, /ابزارهای مدیریتی زیرسامانه/);
  assert.match(source, /ابزارهای استخراج و تحلیل/);
  assert.match(source, /TOOLS_TAB_ATTRIBUTE/);
  assert.match(source, /repeat\(auto-fit,minmax\(175px,1fr\)\)/);
  assert.match(source, /مدیریت فرصت‌ها/);
  assert.match(source, /مرکز بازبینی AI/);
  assert.match(source, /زمان‌بندی استخراج و AI/);
  assert.match(source, /مرکز تحلیل فراخوان‌ها/);
  assert.match(source, /موتور تحلیل PDP/);
  assert.match(source, /تنظیمات تحلیل واقعی/);
  assert.match(source, /پایش مصرف اینترنت/);
  assert.match(source, /InternetUsageMonitoringPanel/);
  assert.match(source, /۱۰ ابزار/);
  assert.doesNotMatch(source, /MutationObserver/);
  assert.doesNotMatch(source, /setInterval/);
});

test("internet usage monitoring remains passive, lazy, and transparent about coverage", async () => {
  const panel = await readFile(new URL("../app/procurement/InternetUsageMonitoringPanel.tsx", import.meta.url), "utf8");
  assert.match(panel, /internet-usage-dashboard/);
  assert.match(panel, /پسیو، خواندنی و بدون دخالت در عملیات/);
  assert.match(panel, /داده اندازه‌گیری‌نشده با عدد تخمینی نمایش داده نمی‌شود/);
  assert.match(panel, /شنود بسته/);
  assert.match(panel, /۲۴ ساعت گذشته/);
  assert.match(panel, /۷ روز گذشته/);
  assert.match(panel, /کل دوره/);
  assert.match(panel, /مصرف به تفکیک فعالیت و بازه زمانی/);
  assert.match(panel, /اندازه‌گیری نشده/);
  assert.doesNotMatch(panel, /آخرین اجراهای استخراج/);
});

test("workflow metadata is bounded to current-page ids without notice-detail fan-out", async () => {
  const source = await readFile(actionsPath, "utf8");
  const backend = await readFile(metadataPath, "utf8");
  assert.match(source, /WORKFLOW_META_API/);
  assert.match(source, /notice_ids/);
  assert.match(source, /direct_ids/);
  assert.doesNotMatch(source, /fetchAll/);
  assert.doesNotMatch(source, /notices\/\$\{item\.notice\}/);
  assert.doesNotMatch(source, /setInterval/);
  assert.doesNotMatch(source, /MutationObserver/);
  assert.match(backend, /MAX_PAGE_IDS = 100/);
  assert.match(backend, /notice_id__in=notice_ids/);
  assert.match(backend, /id__in=direct_ids/);
  assert.match(backend, /submission_document_count=Count\("submission_documents"\)/);
});

test("adds safe remove-from-selected actions without deleting the notice", async () => {
  const source = await readFile(actionsPath, "utf8");
  const backend = await readFile(new URL("../backend/procurement/views_case_actions.py", import.meta.url), "utf8");
  assert.match(source, /حذف از منتخب/);
  assert.match(source, /method: "DELETE"/);
  assert.match(source, /\$\{CASES_API\}\/\$\{meta\.id\}\//);
  assert.match(source, /خود مناقصه\/استعلام و سابقه تحلیل حذف نمی‌شود/);
  assert.match(backend, /DestroyModelMixin/);
  assert.match(backend, /instance\.submission_documents\.exists\(\)/);
  assert.match(backend, /notice_deleted": False/);
});

test("uploads optional submission files and changes stage only after successful uploads", async () => {
  const source = await readFile(actionsPath, "utf8");
  assert.match(source, /const DOCUMENTS_API = `\$\{PROCUREMENT_API\}\/submission-documents`/);
  assert.match(source, /new FormData\(\)/);
  assert.match(source, /body\.append\("case", uploadTarget\.id\)/);
  assert.match(source, /body\.append\("direct_opportunity", uploadTarget\.id\)/);
  assert.match(source, /body\.append\("file", file\)/);
  assert.match(source, /JSON\.stringify\(\{ stage: "submitted" \}\)/);
  assert.match(source, /type="file" multiple/);
  assert.doesNotMatch(source, /type="file" multiple required/);
  assert.match(source, /بدون فایل نیز ثبت ارسال انجام می‌شود/);
});

test("direct opportunities use current-page data for selection and selected submission actions", async () => {
  const source = await readFile(actionsPath, "utf8");
  assert.match(source, /pdp-procurement-direct-page-data/);
  assert.match(source, /SELECTABLE_DIRECT_STAGES/);
  assert.match(source, /updateDirectStage\(item, "selected"\)/);
  assert.match(source, /updateDirectStage\(item, "reviewing"\)/);
  assert.match(source, /مدارک و ثبت ارسال/);
});
