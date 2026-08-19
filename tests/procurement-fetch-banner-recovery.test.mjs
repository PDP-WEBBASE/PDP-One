import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync("app/procurement/ProcurementWorkspaceV14.tsx", "utf8");

test("transient procurement fetch banner re-probes the exact failed endpoint and only clears the matching failure", () => {
  assert.match(source, /const FETCH_RECOVERY_ATTEMPTS = 3/);
  assert.match(source, /const FETCH_RECOVERY_DELAY_MS = 2_500/);
  assert.match(source, /async function probeFailedEndpoint\(failure: FetchFailure\)/);
  assert.match(source, /__pdpProcurementNativeFetch/);
  assert.match(source, /nativeFetch\(failure\.url/);
  assert.match(source, /response\.ok && \(response\.headers\.get\("content-type"\) \|\| ""\)\.includes\("application\/json"\)/);
  assert.match(source, /current\?\.url === failure\.url && current\.at === failure\.at \? null : current/);
});

test("fetch recovery remains bounded and persistent endpoint failures keep the warning visible", () => {
  assert.match(source, /for \(let attempt = 1; attempt <= FETCH_RECOVERY_ATTEMPTS; attempt \+= 1\)/);
  assert.match(source, /if \(attempt > 1\) await wait\(FETCH_RECOVERY_DELAY_MS\)/);
  assert.doesNotMatch(source, /setFetchFailure\(null\);/);
});

test("manual retry is targeted and no longer reloads the entire procurement workspace", () => {
  assert.match(source, /const retryFailedEndpoint = async \(\) =>/);
  assert.match(source, /onClick=\{\(\) => void retryFailedEndpoint\(\)\}/);
  assert.match(source, /disabled=\{retryingFailure\}/);
  assert.doesNotMatch(source, /window\.location\.reload\(\)/);
});
