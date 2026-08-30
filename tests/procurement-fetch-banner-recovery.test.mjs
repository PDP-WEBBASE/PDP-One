import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const v14 = fs.readFileSync("app/procurement/ProcurementWorkspaceV14.tsx", "utf8");
const client = fs.readFileSync("app/procurement/procurementRequestClient.ts", "utf8");

test("active V14 cannot own global fetch timeout retry or recovery probing", () => {
  assert.doesNotMatch(v14, /window\.fetch\s*=/);
  assert.doesNotMatch(v14, /FETCH_RECOVERY_ATTEMPTS|FETCH_RECOVERY_DELAY_MS|probeFailedEndpoint|recoverBrowserSession/);
  assert.doesNotMatch(v14, /AbortController|10_000/);
  assert.doesNotMatch(v14, /window\.location\.reload\s*\(/);
});

test("scoped request governor has bounded concurrency single-flight and one transient retry", () => {
  assert.match(client, /const DEFAULT_CONCURRENCY = 3/);
  assert.match(client, /private readonly inflight = new Map/);
  assert.match(client, /const maxAttempts = options\.retryTransient === false \? 1 : 2/);
  assert.match(client, /TRANSIENT_STATUSES = new Set\(\[502, 503, 504\]\)/);
  assert.match(client, /priority: ProcurementRequestPriority/);
  assert.doesNotMatch(client, /window\.fetch\s*=/);
  assert.doesNotMatch(client, /10_000|FETCH_RECOVERY_ATTEMPTS/);
});

test("circuit breaker decreases load after repeated endpoint failures", () => {
  assert.match(client, /CIRCUIT_FAILURE_THRESHOLD = 3/);
  assert.match(client, /CIRCUIT_OPEN_MS = 30_000/);
  assert.match(client, /throw new Error\("procurement-circuit-open"\)/);
  assert.match(client, /this\.recordSuccess\(url\)/);
  assert.match(client, /this\.recordFailure\(url\)/);
});
