import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const boundary = fs.readFileSync("app/procurement/ProcurementInitialRenderBoundary.tsx", "utf8");

test("initial render readiness is structural and not coupled to dashboard API data", () => {
  assert.match(boundary, /#pdp-procurement-compact-dashboard-host/);
  assert.match(boundary, /data-pdp-management-tools-stable-ready/);
  assert.doesNotMatch(boundary, /querySelector\("\.pdp-compact-dashboard-box"\)/);
});

test("loading shell matches approved header without the removed live API banner", () => {
  assert.doesNotMatch(boundary, /متصل به API و پایگاه‌داده واقعی سامانه/);
});
