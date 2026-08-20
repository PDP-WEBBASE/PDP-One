import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
}

function environment() {
  return { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } };
}

function executionContext() {
  return { waitUntil() {}, passThroughOnException() {} };
}

test("renders development preview metadata", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    environment(),
    executionContext(),
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  assert.match(await response.text(), developmentPreviewMeta);
});

test("routes procurement through V23 while preserving V22 to V13 and stable overlays", async () => {
  const page = await readFile(new URL("../app/procurement/page.tsx", import.meta.url), "utf8");
  const versions = new Map();
  for (let version = 13; version <= 23; version += 1) {
    versions.set(version, await readFile(new URL(`../app/procurement/ProcurementWorkspaceV${version}.tsx`, import.meta.url), "utf8"));
  }
  const pagination = await readFile(new URL("../app/procurement/ProcurementPaginationStableEnhancement.tsx", import.meta.url), "utf8");
  const managementTools = await readFile(new URL("../app/procurement/ProcurementManagementToolsStableEnhancement.tsx", import.meta.url), "utf8");
  assert.match(page, /ProcurementWorkspaceV23/);
  assert.match(versions.get(23), /ProcurementWorkspaceV22/);
  assert.match(versions.get(23), /ProcurementPaginationStableEnhancement/);
  assert.match(versions.get(23), /ProcurementManagementToolsStableEnhancement/);
  assert.doesNotMatch(versions.get(23), /ProcurementWorkspaceEnhancements/);
  assert.doesNotMatch(versions.get(23), /ProcurementSubmissionResultsEnhancements/);
  for (let version = 22; version > 13; version -= 1) {
    assert.match(versions.get(version), new RegExp(`ProcurementWorkspaceV${version - 1}`));
  }
  assert.match(pagination, /COMPACT_NOTICE_PATH/);
  assert.match(pagination, /workflowCode/);
  assert.doesNotMatch(pagination, /fetchAll/);
  assert.doesNotMatch(versions.get(22), /fetchCompleteRecommended/);
  assert.match(managementTools, /ProcurementAnalysisCenterPanel/);
  assert.match(managementTools, /AutomationControlPanel/);
  assert.match(managementTools, /ManagementDashboardPanel/);
  assert.match(managementTools, /CaseFollowUpPanel/);
  assert.match(managementTools, /CaseContractDraftPanel/);
  assert.match(managementTools, /AIReviewCenterPanel/);
  assert.match(managementTools, /OpportunityWorkflowPanel/);
  assert.match(versions.get(14), /AnalysisContextManager/);
  assert.match(versions.get(14), /AnalysisEnginePanel/);
  assert.match(versions.get(13), /متصل به API و پایگاه‌داده واقعی سامانه/);
  assert.doesNotMatch(versions.get(13), /Preview تعاملی/);
  assert.doesNotMatch(versions.get(13), /const notices\s*:/);
  assert.doesNotMatch(versions.get(13), /const directReferrals\s*:/);
  assert.doesNotMatch(versions.get(13), /const extractionHistory\s*=/);
});

test("loads live procurement collections and performs real writes", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");
  assert.match(source, /const PROCUREMENT_API = `\$\{API_BASE\}\/procurement`/);
  assert.match(source, /\$\{PROCUREMENT_API\}\/notices\//);
  assert.match(source, /\$\{PROCUREMENT_API\}\/direct-opportunities\//);
  assert.match(source, /\$\{PROCUREMENT_API\}\/dashboard\//);
  assert.match(source, /\$\{PROCUREMENT_API\}\/extraction-runs\//);
  assert.match(source, /\$\{PROCUREMENT_API\}\/automation-settings\//);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /mode:\s*modeValue/);
  assert.match(source, /connector_ids/);
  assert.match(source, /lookback_days/);
  assert.match(source, /X-CSRFToken/);
  assert.match(source, /داده نمونه نمایش داده نمی‌شود/);
});

test("keeps approved V12 structure and compact list enhancements", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");
  assert.match(source, /قیف مدیریتی/);
  assert.match(source, /برد و باخت/);
  assert.match(source, /جمع‌بندی مدیریتی ChatGPT/);
  assert.match(source, /پرونده‌های فعال/);
  assert.match(source, /نتیجه موفق/);
  assert.match(source, /هشدارهای مدیریتی/);
  assert.match(source, /تصمیم انسانی/);
  assert.match(source, /اقدام بعدی/);
  assert.match(source, /مسئول/);
  assert.match(source, /مهلت/);
});

test("does not silently replace API failures with sample procurement data", async () => {
  const source = await readFile(new URL("../app/procurement/ProcurementWorkspaceV13.tsx", import.meta.url), "utf8");
  assert.match(source, /setLoadError/);
  assert.match(source, /داده نمونه نمایش داده نمی‌شود/);
  assert.doesNotMatch(source, /fallbackNotices/);
  assert.doesNotMatch(source, /sampleNotices/);
});

test("analysis settings are persisted through versioned live APIs", async () => {
  const source = await readFile(new URL("../app/procurement/AnalysisContextManager.tsx", import.meta.url), "utf8");
  assert.match(source, /analysis-context\/active/);
  assert.match(source, /analysis-context\/versions/);
  assert.match(source, /analysis-context\/activate/);
  assert.match(source, /analysis-context\/draft/);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /X-CSRFToken/);
});

test("PDP engine creates guarded requests and keeps results as human-reviewed drafts", async () => {
  const source = await readFile(new URL("../app/procurement/AnalysisEnginePanel.tsx", import.meta.url), "utf8");
  assert.match(source, /analysis-engine\/requests/);
  assert.match(source, /analysis-engine\/runs/);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /X-CSRFToken/);
  assert.match(source, /پیش‌نویس/);
});
