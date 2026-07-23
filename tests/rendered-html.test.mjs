import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
}

function environment() {
  return {
    ASSETS: {
      fetch: async () => new Response("Not found", { status: 404 }),
    },
  };
}

function executionContext() {
  return {
    waitUntil() {},
    passThroughOnException() {},
  };
}

test("renders development preview metadata", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    environment(),
    executionContext(),
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  assert.match(await response.text(), developmentPreviewMeta);
});

test("keeps source controls and extraction health inside management", async () => {
  const pageSource = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");
  const workspaceSource = await readFile(new URL("../app/procurement/ProcurementWorkspaceV11.tsx", import.meta.url), "utf8");

  assert.doesNotMatch(pageSource, /ConnectorHealthBanner/);
  assert.doesNotMatch(pageSource, /ExtractionSourceControls/);
  assert.match(workspaceSource, /گزارش استخراج/);
  assert.match(workspaceSource, /<ConnectorHealthBanner embedded/);
  assert.match(workspaceSource, /<ExtractionSourceControls/);
  assert.match(workspaceSource, /نقش و Prompt/);
  assert.match(workspaceSource, /کلیدواژه‌ها/);
  assert.match(workspaceSource, /پروفایل، صلاحیت و رزومه/);
  assert.match(workspaceSource, /نسخه‌ها و فعال‌سازی/);
  assert.doesNotMatch(workspaceSource, /تنظیمات کنترل‌شده/);
  assert.doesNotMatch(workspaceSource, /ساختار زیرتب‌های تأییدشده قبلی حفظ شده است/);
});

test("preserves approved dashboard and adds only requested list enhancements", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV11.tsx", import.meta.url), "utf8");

  assert.match(source, /قیف مدیریتی/);
  assert.match(source, /برد و باخت/);
  assert.match(source, /جمع‌بندی مدیریتی ChatGPT/);
  assert.match(source, /پرونده‌های فعال/);
  assert.match(source, /کل مناقصات/);
  assert.match(source, /کل استعلامات/);
  assert.match(source, /کل ارجاعات مستقیم/);
  assert.match(source, /ثبت ارجاع مستقیم جدید/);
  assert.match(source, /compactViewStyle/);
  assert.match(source, /sourceBadgeStyle/);
  assert.match(source, /اهمیت/);
});
