import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("startup session resilience is installed before the active procurement fetch guards", async () => {
  const workspace = await read("app/procurement/ProcurementWorkspaceV23.tsx");
  const startup = workspace.indexOf("<ProcurementStartupSessionResilience />");
  const pagination = workspace.indexOf("<ProcurementPaginationStableEnhancement />");
  const baseWorkspace = workspace.indexOf("<ProcurementWorkspaceV22 />");

  assert.ok(startup >= 0, "startup session resilience must be mounted");
  assert.ok(pagination > startup, "startup session resilience must precede stable pagination fetch wrapping");
  assert.ok(baseWorkspace > pagination, "startup resilience must be active before V14 installs its fetch guard");
});

test("session startup gets bounded retries without changing ordinary procurement endpoint timeouts", async () => {
  const source = await read("app/procurement/ProcurementStartupSessionResilience.tsx");
  const guard = await read("app/procurement/ProcurementWorkspaceV14.tsx");

  assert.match(source, /SESSION_PATH = "\/api\/v1\/auth\/session\/"/);
  assert.match(source, /SESSION_ATTEMPT_TIMEOUT_MS = 15_000/);
  assert.match(source, /SESSION_MAX_ATTEMPTS = 2/);
  assert.match(source, /pdp_reset_session/);
  assert.match(source, /cache: "no-store"/);
  assert.doesNotMatch(source, /window\.location\.reload/);

  assert.match(guard, /}, 10_000\);/);
  assert.match(guard, /parsed\.pathname\.startsWith\("\/api\/v1\/procurement\/"\)/);
});
