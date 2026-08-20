import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const wrapperPath = new URL("../app/procurement/ProcurementWorkspaceV23.tsx", import.meta.url);
const overlayPath = new URL("../app/procurement/ProcurementCompactWorkspaceStableEnhancement.tsx", import.meta.url);
const backendPath = new URL("../backend/procurement/views_compact_ui.py", import.meta.url);
const urlsPath = new URL("../backend/procurement/urls.py", import.meta.url);

test("mounts the stable compact procurement enhancement after the page-bounded workflow overlay", async () => {
  const wrapper = await readFile(wrapperPath, "utf8");
  assert.match(wrapper, /ProcurementCompactWorkspaceStableEnhancement/);
  assert.match(wrapper, /<ProcurementWorkflowActionsStableEnhancement \/>\s*<ProcurementCompactWorkspaceStableEnhancement \/>/);
  assert.doesNotMatch(wrapper, /ProcurementSubmissionResultsEnhancements/);
});

test("shows all canonical sources in Setad Hezareh Parsnamad priority without rewriting data", async () => {
  const frontend = await readFile(overlayPath, "utf8");
  const backend = await readFile(backendPath, "utf8");
  assert.match(frontend, /ستاد/);
  assert.match(frontend, /هزاره/);
  assert.match(frontend, /پارس/);
  assert.match(frontend, /item\.sources\.length > 1/);
  assert.match(backend, /source_links\.all\(\)/);
  assert.match(backend, /"sources"/);
  assert.doesNotMatch(backend, /NoticeSourceLink\.objects\.create/);
});

test("keeps bulk recommendation dismissal limited to tender inquiry recommended views and preserves notices", async () => {
  const frontend = await readFile(overlayPath, "utf8");
  const backend = await readFile(backendPath, "utf8");
  assert.match(frontend, /activeWorkflow\(\) === "پیشنهادی"/);
  assert.match(frontend, /top !== "مناقصات" && top !== "استعلامات"/);
  assert.match(frontend, /حذف گروهی پیشنهادها/);
  assert.match(backend, /latest_effective_recommended_notice_ids/);
  assert.match(backend, /NoticeAnalysisDraft\.ReviewStatus\.REJECTED/);
  assert.match(backend, /"notice_deleted": False/);
  assert.doesNotMatch(backend, /ProcurementNotice\.objects\.filter\([^\n]+\)\.delete/);
});

test("adds deadline state and publication-date filters and removes redundant processing presentation", async () => {
  const frontend = await readFile(overlayPath, "utf8");
  const backend = await readFile(backendPath, "utf8");
  assert.match(frontend, /وضعیت مهلت/);
  assert.match(frontend, /تاریخ انتشار/);
  assert.match(frontend, /پردازش:/);
  assert.match(frontend, /style\.display = "none"/);
  assert.match(backend, /deadline_status/);
  assert.match(backend, /published_on/);
});

test("dashboard uses server-side analysis statistics and overall tender inquiry breakdowns", async () => {
  const frontend = await readFile(overlayPath, "utf8");
  const backend = await readFile(backendPath, "utf8");
  assert.match(backend, /procurement_analysis_statistics\(\)/);
  assert.match(backend, /active_run\.get\("remaining"\)/);
  assert.match(backend, /"tender"/);
  assert.match(backend, /"inquiry"/);
  assert.match(frontend, /محاسبه مستقیم سمت سرور/);
  assert.match(frontend, /مناقصه/);
  assert.match(frontend, /استعلام/);
  assert.match(frontend, /normalize\(node\.textContent\) === "داده واقعی"/);
});

test("routes the compact UI feed dashboard and bulk-dismiss endpoints", async () => {
  const urls = await readFile(urlsPath, "utf8");
  assert.match(urls, /ui\/notices\//);
  assert.match(urls, /ui\/dashboard\//);
  assert.match(urls, /ui\/recommendations\/dismiss-bulk\//);
});
