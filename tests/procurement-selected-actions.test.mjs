import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const enhancementsPath = new URL("../app/procurement/ProcurementWorkspaceEnhancements.tsx", import.meta.url);

test("organizes all management tools in a dedicated workspace tab and hides legacy floating launchers", async () => {
  const source = await readFile(enhancementsPath, "utf8");

  assert.match(source, /ابزارهای مدیریتی زیرسامانه/);
  assert.match(source, /ابزارهای استخراج و تحلیل/);
  assert.match(source, /TOOLS_TAB_ATTRIBUTE/);
  assert.match(source, /repeat\(auto-fit,minmax\(175px,1fr\)\)/);
  assert.match(source, /hideLegacyFloatingButtons/);
  assert.match(source, /button\.style\.position === "fixed"/);
  assert.match(source, /button\.style\.display = "none"/);
  assert.match(source, /مدیریت فرصت‌ها/);
  assert.match(source, /مرکز بازبینی AI/);
  assert.match(source, /زمان‌بندی استخراج و AI/);
  assert.match(source, /مرکز تحلیل فراخوان‌ها/);
  assert.match(source, /موتور تحلیل PDP/);
  assert.match(source, /تنظیمات تحلیل واقعی/);
  assert.match(source, /AnalysisContextManager/);
  assert.match(source, /AnalysisEnginePanel/);
  assert.match(source, /۹ ابزار/);
});

test("loads only selected case details instead of paginating the entire tender and inquiry archive", async () => {
  const source = await readFile(enhancementsPath, "utf8");

  assert.match(source, /PRE_SUBMISSION_STAGES\.map/);
  assert.match(source, /\$\{CASES_API\}\/\?stage=\$\{stage\}&ordering=-updated_at/);
  assert.match(source, /\$\{PROCUREMENT_API\}\/notices\/\$\{item\.notice\}\//);
  assert.doesNotMatch(source, /notices\/\?resolved_notice_type=tender/);
  assert.doesNotMatch(source, /notices\/\?resolved_notice_type=inquiry/);
});

test("adds safe remove-from-selected actions without deleting the notice", async () => {
  const source = await readFile(enhancementsPath, "utf8");
  const backend = await readFile(new URL("../backend/procurement/views_case_actions.py", import.meta.url), "utf8");

  assert.match(source, /حذف از منتخب/);
  assert.match(source, /method:\s*"DELETE"/);
  assert.match(source, /\$\{CASES_API\}\/\$\{item\.id\}\//);
  assert.match(source, /خود مناقصه\/استعلام و سابقه تحلیل حذف نمی‌شود/);
  assert.match(backend, /DestroyModelMixin/);
  assert.match(backend, /instance\.submission_documents\.exists\(\)/);
  assert.match(backend, /instance\.delete\(\)/);
  assert.match(backend, /notice_deleted": False/);
  assert.doesNotMatch(backend, /ProcurementNotice\.objects\.filter\([^\n]+\)\.delete/);
});

test("uploads multiple submission files and moves a selected notice case to submitted only after uploads", async () => {
  const source = await readFile(enhancementsPath, "utf8");

  assert.match(source, /const DOCUMENTS_API = `\$\{PROCUREMENT_API\}\/submission-documents`/);
  assert.match(source, /new FormData\(\)/);
  assert.match(source, /body\.append\("case", uploadTarget\.id\)/);
  assert.match(source, /body\.append\("document_type", documentType\)/);
  assert.match(source, /body\.append\("file", file\)/);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /JSON\.stringify\(\{ stage: "submitted" \}\)/);
  assert.match(source, /type="file" multiple required/);
  assert.match(source, /پس از ذخیره موفق همه فایل‌ها/);
  assert.match(source, /اگر بارگذاری یکی از فایل‌ها ناموفق باشد، مرحله پرونده تغییر نمی‌کند/);
});

test("direct opportunities can be selected from all or recommended and use the same selected submission workflow", async () => {
  const source = await readFile(enhancementsPath, "utf8");
  const documents = await readFile(new URL("../backend/procurement/models_documents.py", import.meta.url), "utf8");

  assert.match(source, /کل ارجاعات مستقیم/);
  assert.match(source, /\["کل ارجاعات مستقیم", "پیشنهادی"\]/);
  assert.match(source, /SELECTABLE_DIRECT_STAGES/);
  assert.match(source, /updateDirectStage\(item, "selected"\)/);
  assert.match(source, /body\.append\("direct_opportunity", uploadTarget\.id\)/);
  assert.match(source, /updateDirectStage\(item, "reviewing"\)/);
  assert.match(source, /مدارک و ثبت ارسال/);
  assert.match(documents, /direct_opportunity = models\.ForeignKey/);
  assert.match(documents, /related_name="submission_documents"/);
});
