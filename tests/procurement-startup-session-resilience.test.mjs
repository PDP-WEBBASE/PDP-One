import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("startup compatibility boundary remains mounted without owning browser fetch", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV23.tsx");
  const startup = workspace.indexOf("<ProcurementStartupSessionResilience />");
  const baseWorkspace = workspace.indexOf("<ProcurementWorkspaceV22 />");
  const source = await read("app/procurement/ProcurementStartupSessionResilience.tsx");

  assert.ok(startup >= 0, "startup compatibility boundary must remain mounted");
  assert.ok(baseWorkspace > startup, "compatibility boundary must precede the React-owned workspace chain");
  assert.doesNotMatch(workspace, /ProcurementPaginationStableEnhancement/);
  assert.doesNotMatch(source, /window\.fetch\s*=/, "startup compatibility must never replace window.fetch");
  assert.doesNotMatch(source, /SESSION_ATTEMPT_TIMEOUT_MS|SESSION_MAX_ATTEMPTS|pdp_reset_session/,
    "startup boundary must not own timeout/retry/session recovery policy");
});

test("active V14 is presentation-only and cannot create retry storms", async () => {
  const guard = await read("app/procurement/ProcurementWorkspaceV14.tsx");

  assert.doesNotMatch(guard, /window\.fetch\s*=/, "V14 must not replace browser fetch");
  assert.doesNotMatch(guard, /AbortController|10_000|FETCH_RECOVERY_ATTEMPTS|probeFailedEndpoint|recoverBrowserSession/,
    "V14 must not impose subsystem-wide timeout/retry/probe behaviour");
  assert.match(guard, /Request resilience belongs to scoped data\/session clients/);
});
