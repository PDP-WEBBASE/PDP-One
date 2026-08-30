import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../services/pdp_mcp/interaction_tools.py", import.meta.url), "utf8");
const dockerfile = await readFile(new URL("../services/pdp_mcp/Dockerfile", import.meta.url), "utf8");

test("procurement read remains available without PDPONE WEB arming", () => {
  assert.match(source, /async def query_procurement_notices/);
  assert.match(source, /readOnlyHint=True/);
  assert.match(source, /does not require PDPONE WEB/);
});

test("PDPONE WEB writes use explicit server-side lease tools", () => {
  assert.match(source, /async def arm_pdpone_web_write/);
  assert.match(source, /interaction\/write\/arm/);
  assert.match(source, /async def disarm_pdpone_web_write/);
  assert.match(source, /lease_id/);
  assert.match(source, /conversation_key/);
});

test("ambiguous writes have a pending confirmation path and exact writes require verification", () => {
  assert.match(source, /prepare_procurement_select_confirmation/);
  assert.match(source, /confirm_procurement_select/);
  assert.match(source, /Do not guess notice identity/);
  assert.match(source, /if not result\.get\("verified"\)/);
  assert.match(source, /read-after-write verification/);
});

test("MCP runtime image packages the interaction tool module registered by server.py", () => {
  assert.match(dockerfile, /COPY[^\n]*interaction_tools\.py[^\n]*\.\//);
});
