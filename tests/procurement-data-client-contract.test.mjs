import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../app/procurement/procurementDataClient.ts", import.meta.url), "utf8");
const workspaceCss = await readFile(new URL("../app/procurement/workspace-v4.module.css", import.meta.url), "utf8");

test("procurement data client uses context-owned request/cache primitives", () => {
  assert.match(source, /export function procurementQueryKey/);
  assert.match(source, /new Map<string, ProcurementCacheEntry>/);
  assert.match(source, /new Map<string, Promise<ProcurementQueryPayload>>/);
  assert.match(source, /AbortController/);
  assert.match(source, /abortAllExcept/);
  assert.match(source, /Stale procurement response discarded/);
  assert.match(source, /staleWhileRevalidate/);
  assert.match(source, /prefetch/);
});

test("new data layer never monkey patches global fetch or stores application state on window", () => {
  assert.doesNotMatch(source, /window\.__pdp/);
  assert.doesNotMatch(source, /window\.fetch\s*=/);
  assert.doesNotMatch(source, /document\.addEventListener/);
  assert.doesNotMatch(source, /querySelector/);
});

test("query key includes all context dimensions needed for deterministic cache ownership", () => {
  for (const marker of ["noticeType", "workflow", "page", "pageSize", "sort", "filters"]) {
    assert.match(source, new RegExp(marker));
  }
});

test("uncached active notice load enters browser fetch without a nested pre-network governor", () => {
  assert.doesNotMatch(source, /ProcurementRequestClient/);
  assert.match(source, /private readonly fetchImpl: typeof fetch/);
  assert.match(source, /this\.fetchImpl\(requestUrl/);
  assert.match(source, /private async fetchNoticePayload/);
});

test("native browser fetch is invoked through a receiver-safe wrapper", () => {
  assert.match(source, /options\.fetchImpl \?\? \(\(input, init\) => globalThis\.fetch\(input, init\)\)/);
  assert.doesNotMatch(source, /this\.fetchImpl\s*=\s*options\.fetchImpl\s*\|\|\s*fetch/);
  assert.doesNotMatch(source, /this\.fetchImpl\s*=\s*options\.fetchImpl\s*\?\?\s*fetch/);
  assert.match(source, /Never store the native Window\.fetch function as an unbound instance method/);
});

test("notice retry policy is bounded and abort-aware", () => {
  assert.match(source, /TRANSIENT_STATUSES = new Set\(\[502, 503, 504\]\)/);
  assert.match(source, /for \(let attempt = 1; attempt <= 2; attempt \+= 1\)/);
  assert.match(source, /if \(error instanceof DOMException && error\.name === "AbortError"\) throw error/);
  assert.match(source, /retryableNetworkError = error instanceof TypeError/);
  assert.match(source, /await waitForRetry\(RETRY_DELAY_MS, signal\)/);
});

test("notice owner retains active-view cancellation and generation isolation", () => {
  assert.match(source, /const existing = this\.inflight\.get\(key\)/);
  assert.match(source, /this\.controllers\.get\(key\)\?\.abort\(\)/);
  assert.match(source, /this\.generation\.set\(key, \(this\.generation\.get\(key\) \|\| 0\) \+ 1\)/);
  assert.match(source, /this\.generation\.get\(key\) !== requestGeneration/);
});

test("notice error state cannot simultaneously render the empty-state card", () => {
  assert.match(workspaceCss, /\.message\+\.recordList>\.empty\{display:none\}/);
});
