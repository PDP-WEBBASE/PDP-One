import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../app/procurement/procurementDataClient.ts", import.meta.url), "utf8");

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
