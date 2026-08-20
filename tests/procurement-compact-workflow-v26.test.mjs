import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("../app/procurement/ProcurementCompactWorkflowEnhancement.tsx", import.meta.url), "utf8");
const metrics = fs.readFileSync(new URL("../backend/procurement/views_pagination_metrics.py", import.meta.url), "utf8");
const browse = fs.readFileSync(new URL("../backend/procurement/views_browse.py", import.meta.url), "utf8");
const workspace = fs.readFileSync(new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url), "utf8");

test("compact workflow enhancement is wired before the legacy workspace", () => {
  assert.match(workspace, /ProcurementCompactWorkflowEnhancement/);
  assert.ok(workspace.indexOf("<ProcurementCompactWorkflowEnhancement />") < workspace.indexOf("<ProcurementWorkspaceV22 />"));
});

test("source badges use the required Setad, Hezareh, Pars Namad priority", () => {
  assert.match(source, /includes\("ستاد"\).*return 1/s);
  assert.match(source, /includes\("هزاره"\).*return 2/s);
  assert.match(source, /includes\("پارس"\).*includes\("نماد"\).*return 3/s);
  assert.match(source, /source_links/);
});

test("normal titles wrap fully and only genuinely long titles are clamped", () => {
  assert.match(source, /length > 220/);
  assert.match(source, /whiteSpace = "normal"/);
  assert.match(source, /-webkit-line-clamp/);
});

test("bulk recommendation dismissal is page-scoped and does not delete notices", () => {
  assert.match(source, /حذف پیشنهادهای این صفحه/);
  assert.match(source, /خود مناقصه\/استعلام و سابقه تحلیل حذف نمی‌شود/);
  assert.match(source, /recommended-notices\/.*dismiss/s);
  assert.doesNotMatch(source, /method:\s*"DELETE"/);
});

test("deadline and exact publication filters are server-backed", () => {
  assert.match(source, /browse-notices/);
  assert.match(source, /deadline_state/);
  assert.match(source, /published_on/);
  assert.match(browse, /submission_deadline__lt=now/);
  assert.match(browse, /submission_deadline__lte=now \+ timedelta\(days=DEADLINE_EXPIRING_DAYS\)/);
  assert.match(browse, /published_date=selected_date/);
});

test("dashboard exposes total, tender and inquiry breakdowns", () => {
  assert.match(metrics, /"breakdown"/);
  assert.match(metrics, /"tender"/);
  assert.match(metrics, /"inquiry"/);
  assert.match(metrics, /active_run_remaining/);
  assert.match(source, /شاخص‌های واقعی فراخوان‌ها/);
});

test("redundant processing badge and live database banner are removed from the compact view", () => {
  assert.match(source, /startsWith\("پردازش:"\)/);
  assert.match(source, /PostgreSQL/);
  assert.match(source, /liveBanner\.style\.display = "none"/);
});
