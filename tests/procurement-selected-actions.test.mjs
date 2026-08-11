import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const enhancementsPath = new URL("../app/procurement/ProcurementWorkspaceEnhancements.tsx", import.meta.url);

test("organizes management tools inside the workspace and hides legacy floating launchers", async () => {
  const source = await readFile(enhancementsPath, "utf8");

  assert.match(source, /ابزارهای مدیریتی زیرسامانه/);
  assert.match(source, /repeat\(auto-fit,minmax\(175px,1fr\)\)/);
  assert.match(source, /hideLegacyFloatingButtons/);
  assert.match(source, /button\.style\.position === "fixed"/);
  assert.match(source, /button\.style\.display = "none"/);
  assert.match(source, /مدیریت فرصت‌ها/);
  assert.match(source, /مرکز بازبینی AI/);
  assert.match(source, /زمان‌بندی استخراج و AI/);
  assert.match(source, /مرکز تحلیل فراخوان‌ها/);
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

test("uploads multiple submission files and moves the selected case to submitted only after uploads", async () => {
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
