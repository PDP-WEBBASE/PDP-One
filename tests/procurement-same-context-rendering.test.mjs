import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const dataClient = await readFile(new URL("../app/procurement/procurementDataClient.ts", import.meta.url), "utf8");
const guard = await readFile(new URL("../app/procurement/ProcurementNoticeContextRenderGuard.tsx", import.meta.url), "utf8");
const composition = await readFile(new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url), "utf8");

test("cold notice contexts publish lifecycle ownership while same-context cache remains immediate", () => {
  assert.match(dataClient, /PROCUREMENT_NOTICE_CONTEXT_LIFECYCLE_EVENT/);
  assert.match(dataClient, /if \(!cached\) \{\s*emitNoticeContextLifecycle\(context, "cold-start"\)/s);
  assert.match(dataClient, /emitNoticeContextLifecycle\(context, "success"\)/);
  assert.match(dataClient, /aborted \? "aborted" : "error"/);
  assert.match(dataClient, /void this\.load<T>\(context\)[\s\S]*return cached;/);
});

test("render guard is presentation-only and never becomes a navigation or network owner", () => {
  assert.match(guard, /PROCUREMENT_NOTICE_CONTEXT_LIFECYCLE_EVENT/);
  assert.doesNotMatch(guard, /\bfetch\s*\(/);
  assert.doesNotMatch(guard, /querySelector|MutationObserver|\.click\s*\(/);
  assert.doesNotMatch(guard, /setProcurementStableViewState/);
  assert.match(guard, /data-pdp-shared-notice-layout/);
  assert.match(guard, /nth-last-of-type\(2\)/);
  assert.match(guard, /last-of-type/);
});

test("cold transition hides previous notice payload until the new context settles", () => {
  assert.match(guard, /detail\.phase === "cold-start"/);
  assert.match(guard, /detail\.key !== pendingKey\.current/);
  assert.match(guard, /detail\.phase === "success"/);
  assert.match(guard, /requestAnimationFrame/);
  assert.match(guard, /detail\.phase === "error"/);
  assert.match(guard, /داده تب قبلی عمداً نمایش داده نمی‌شود/);
});

test("guard is integrated after the canonical workspace and does not touch direct referrals", () => {
  assert.match(composition, /import ProcurementNoticeContextRenderGuard/);
  assert.match(composition, /<ProcurementWorkspaceV22\s*\/>\s*<ProcurementNoticeContextRenderGuard\s*\/>/s);
  assert.doesNotMatch(guard, /direct-opportunities|data-pdp-shared-notice-layout="direct"/);
});
