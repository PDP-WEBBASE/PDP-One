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

test("routes procurement to the live V13 workspace", async () => {
  const pageSource = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");
  const workspaceSource = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /ProcurementWorkspaceV13/);
  assert.match(workspaceSource, /متصل به API و پایگاه‌داده واقعی سامانه/);
  assert.doesNotMatch(workspaceSource, /Preview تعاملی/);
  assert.doesNotMatch(workspaceSource, /const notices\s*:/);
  assert.doesNotMatch(workspaceSource, /const directReferrals\s*:/);
  assert.doesNotMatch(workspaceSource, /const extractionHistory\s*=/);
});

test("loads live procurement collections and performs real writes", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");

  assert.match(source, /\/procurement\/notices\//);
  assert.match(source, /\/procurement\/direct-opportunities\//);
  assert.match(source, /\/procurement\/dashboard\//);
  assert.match(source, /\/procurement\/extraction-runs\//);
  assert.match(source, /\/procurement\/automation-settings\//);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /mode:\s*modeValue/);
  assert.match(source, /connector_ids/);
  assert.match(source, /lookback_days/);
  assert.match(source, /X-CSRFToken/);
  assert.match(source, /داده نمونه نمایش داده نمی‌شود/);
});

test("keeps approved V12 structure and compact list enhancements", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");

  assert.match(source, /قیف مدیریتی/);
  assert.match(source, /برد و باخت/);
  assert.match(source, /جمع‌بندی مدیریتی ChatGPT/);
  assert.match(source, /پرونده‌های فعال/);
  assert.match(source, /کل مناقصات/);
  assert.match(source, /کل استعلامات/);
  assert.match(source, /کل ارجاعات مستقیم/);
  assert.match(source, /ثبت ارجاع مستقیم جدید/);
  assert.match(source, /compactRecordStyle/);
  assert.match(source, /compactViewStyle/);
  assert.match(source, /sourceBadgeStyle/);
  assert.match(source, /importanceStyles/);
  assert.match(source, /همه فوریت‌ها/);
  assert.match(source, /urgencyFilter/);
  assert.doesNotMatch(source, /<dt>اقدام بعدی<\/dt>/);
  assert.match(source, /fontSize:21/);
});

test("does not silently replace API failures with sample procurement data", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");

  assert.match(source, /داده نمونه نمایش داده نمی‌شود/);
  assert.match(source, /هیچ داده نمونه‌ای جایگزین نشده است/);
  assert.match(source, /رکورد واقعی مطابق این فیلتر وجود ندارد/);
  assert.match(source, /هنوز استخراج واقعی ثبت نشده است/);
});
