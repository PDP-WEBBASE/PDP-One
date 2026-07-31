import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return readFile(new URL(path, import.meta.url), "utf8");
}

test("AI review center uses live draft and summary APIs", async () => {
  const panel = await source("../app/procurement/AIReviewCenterPanel.tsx");

  assert.match(panel, /analysis-drafts\/\?ordering=-analyzed_at/);
  assert.match(panel, /analysis\/review-summary\//);
  assert.match(panel, /credentials:\s*"include"/);
  assert.match(panel, /X-CSRFToken/);
  assert.doesNotMatch(panel, /const\s+sample/i);
  assert.doesNotMatch(panel, /mock/i);
});

test("review decisions and selection require explicit POST actions", async () => {
  const panel = await source("../app/procurement/AIReviewCenterPanel.tsx");

  assert.match(panel, /decision:\s*"approved"/);
  assert.match(panel, /decision:\s*"rejected"/);
  assert.match(panel, /decision:\s*"needs_revision"/);
  assert.match(panel, /method:\s*"POST"/);
  assert.match(panel, /\/review\//);
  assert.match(panel, /\/select\//);
  assert.match(panel, /هر تصمیم و تبدیل فقط با اقدام صریح مدیر انجام می‌شود/);
  assert.match(panel, /برای رد یا بازگشت جهت تکمیل، توضیح الزامی است/);
});

test("review center does not create contracts or finance records", async () => {
  const panel = await source("../app/procurement/AIReviewCenterPanel.tsx");

  assert.doesNotMatch(panel, /contracts\//);
  assert.doesNotMatch(panel, /receivables\//);
  assert.doesNotMatch(panel, /payment-receipts\//);
  assert.doesNotMatch(panel, /method:\s*"DELETE"/);
});

test("V16 preserves the approved opportunity workflow", async () => {
  const wrapper = await source("../app/procurement/ProcurementWorkspaceV16.tsx");

  assert.match(wrapper, /ProcurementWorkspaceV15/);
  assert.match(wrapper, /AIReviewCenterPanel/);
  assert.match(wrapper, /مرکز بازبینی AI/);
});
