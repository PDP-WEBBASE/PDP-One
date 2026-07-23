import assert from "node:assert/strict";
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

test("renders independent tender and inquiry controls for extraction sources", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("http://localhost/procurement", {
      headers: { accept: "text/html" },
    }),
    environment(),
    executionContext(),
  );

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /منابع استخراج/);
  assert.match(html, /مناقصات و استعلامات هر سایت مستقل هستند/);
  assert.match(html, /پارس‌نماد داده/);
  assert.match(html, /همان محتوای استعلامات/);
});
