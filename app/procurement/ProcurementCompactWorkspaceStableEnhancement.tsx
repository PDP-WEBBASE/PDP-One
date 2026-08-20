"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type SourceBadge = {
  key: string;
  name: string;
  source_url: string;
  detail_url: string;
};

type CompactNotice = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  published_date: string | null;
  submission_deadline: string | null;
  source_name: string;
  source_url: string;
  detail_url: string;
  sources: SourceBadge[];
  first_seen_at?: string;
  is_recommended?: boolean;
  [key: string]: unknown;
};

type NoticePayload = {
  count: number;
  page: number;
  page_size: number;
  results: CompactNotice[];
  next?: string | null;
  previous?: string | null;
};

type CountBreakdown = { total: number; tender: number; inquiry: number };
type DashboardPayload = {
  generated_at: string;
  metrics: {
    all_notices: CountBreakdown;
    new_today: CountBreakdown;
    analysis_remaining: CountBreakdown;
    recommended: CountBreakdown;
    selected: CountBreakdown;
    submitted: CountBreakdown;
    near_deadline: CountBreakdown;
    successful_results: CountBreakdown;
  };
  management: { overdue_actions: number; without_responsible: number; direct_active: number };
  analysis: { basis: string; run_id: string | null; run_status: string | null };
};

type SourcePayload = Array<{ name: string; key?: string }> | { results?: Array<{ name: string; key?: string }> };
type CompactWindow = Window & {
  __pdpPaginationNativeFetch?: typeof window.fetch;
  __pdpPaginationPage?: number;
  __pdpPaginationPageSize?: number;
  __pdpCompactFetchInstalled?: boolean;
  __pdpCompactInnerFetch?: typeof window.fetch;
  __pdpCompactDeadlineStatus?: string;
  __pdpCompactPublishedOn?: string;
  __pdpCompactLastTop?: string;
  __pdpCompactAbortController?: AbortController;
};

type UiState = { top: string; workflow: string };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const NOTICE_PATH = `${PROCUREMENT_API}/notices/`;
const RECOMMENDED_PATH = `${PROCUREMENT_API}/recommended-notices/`;
const COMPACT_NOTICE_PATH = `${PROCUREMENT_API}/ui/notices/`;
const COMPACT_DASHBOARD_PATH = `${PROCUREMENT_API}/ui/dashboard/`;
const BULK_DISMISS_PATH = `${PROCUREMENT_API}/ui/recommendations/dismiss-bulk/`;
const DATA_EVENT = "pdp-procurement-compact-notice-data";
const PAGINATION_META_EVENT = "pdp-procurement-pagination-meta";
const FILTER_HOST_ID = "pdp-procurement-compact-filter-host";
const DASHBOARD_HOST_ID = "pdp-procurement-compact-dashboard-host";
const TOP_LABELS = new Set(["داشبورد مدیریتی", "مناقصات", "استعلامات", "ارجاعات مستقیم", "مدیریت زیرسامانه"]);
const WORKFLOW_LABELS = new Set([
  "مناقصات ۳ روز اخیر", "استعلامات ۳ روز اخیر", "کل مناقصات", "کل استعلامات", "کل ارجاعات مستقیم",
  "پیشنهادی", "منتخب", "ارسال‌شده", "نتایج",
]);
const fa = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" });
const faDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" });
const DASHBOARD_TTL_MS = 60 * 1000;

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function selectedButtonLabel(labels: Set<string>, excludeNav = false) {
  const selected = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((button) => {
    if (excludeNav && button.closest("nav")) return false;
    const label = normalize(button.textContent);
    if (!labels.has(label)) return false;
    if (button.getAttribute("aria-selected") === "true" || button.getAttribute("aria-pressed") === "true") return true;
    return Boolean(normalize(button.getAttribute("class")));
  });
  return normalize(selected?.textContent);
}

function activeTopTab() {
  return selectedButtonLabel(TOP_LABELS);
}

function activeWorkflow() {
  return selectedButtonLabel(WORKFLOW_LABELS, true);
}

function currentUiState(): UiState {
  return { top: activeTopTab(), workflow: activeWorkflow() };
}

function findWorkflowSection() {
  const workflow = activeWorkflow();
  if (!workflow) return null;
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((candidate) =>
    normalize(candidate.textContent) === workflow && Boolean(normalize(candidate.getAttribute("class"))),
  );
  return button?.closest("section") || null;
}

function fieldValue(labelPrefix: string) {
  const section = findWorkflowSection();
  const root: ParentNode = section || document;
  const label = Array.from(root.querySelectorAll<HTMLLabelElement>("label")).find((candidate) =>
    normalize(candidate.textContent).startsWith(labelPrefix),
  );
  const field = label?.querySelector<HTMLInputElement | HTMLSelectElement>("input,select");
  return normalize(field?.value);
}

function sourceRank(value: string) {
  const token = value.toLocaleLowerCase("fa");
  if (token.includes("setad") || token.includes("ستاد")) return 0;
  if (token.includes("hezareh") || token.includes("هزاره")) return 1;
  if (token.includes("parsnamad") || token.includes("پارس")) return 2;
  return 3;
}

function sourceSort<T extends { name: string }>(a: T, b: T) {
  const rank = sourceRank(a.name) - sourceRank(b.name);
  return rank || a.name.localeCompare(b.name, "fa");
}

function workflowCode(label: string, forceRecommended = false) {
  if (forceRecommended || label === "پیشنهادی") return "recommended";
  if (label === "منتخب") return "selected";
  if (label === "ارسال‌شده") return "submitted";
  if (label === "نتایج") return "results";
  return "recent";
}

function noticeTypeForTop(top: string) {
  return top === "مناقصات" ? "tender" : top === "استعلامات" ? "inquiry" : "";
}

function synchronizeCompactTop(top: string) {
  const guarded = window as CompactWindow;
  if (guarded.__pdpCompactLastTop && guarded.__pdpCompactLastTop !== top) {
    guarded.__pdpCompactDeadlineStatus = "";
    guarded.__pdpCompactPublishedOn = "";
    guarded.__pdpPaginationPage = 1;
  }
  guarded.__pdpCompactLastTop = top;
}

function buildCompactQuery(forceRecommended = false) {
  const guarded = window as CompactWindow;
  const top = activeTopTab();
  synchronizeCompactTop(top);
  const params = new URLSearchParams();
  params.set("notice_type", noticeTypeForTop(top));
  params.set("workflow", workflowCode(activeWorkflow(), forceRecommended));
  params.set("page", String(Math.max(1, guarded.__pdpPaginationPage || 1)));
  params.set("page_size", String(Math.min(100, Math.max(1, guarded.__pdpPaginationPageSize || 50))));
  const common: Array<[string, string]> = [
    ["search", fieldValue("جست‌وجو")],
    ["source_name", fieldValue("منبع")],
    ["province", fieldValue("استان")],
    ["importance", fieldValue("اهمیت")],
    ["urgency", fieldValue("فوریت")],
    ["deadline_status", guarded.__pdpCompactDeadlineStatus || ""],
    ["published_on", guarded.__pdpCompactPublishedOn || ""],
  ];
  common.forEach(([key, value]) => { if (value) params.set(key, value); });
  return params;
}

function normalizeCompactPayload(payload: NoticePayload, workflow: string): NoticePayload {
  return {
    ...payload,
    next: null,
    previous: null,
    results: payload.results.map((item) => {
      const normalizedItem: CompactNotice = { ...item };
      if (workflow === "recent" && item.published_date) {
        normalizedItem.first_seen_at = `${item.published_date}T12:00:00+03:30`;
      }
      if (workflow === "recommended") normalizedItem.is_recommended = true;
      return normalizedItem;
    }),
  };
}

function jsonResponse(response: Response, payload: unknown) {
  const headers = new Headers(response.headers);
  headers.set("Content-Type", "application/json");
  headers.delete("Content-Length");
  headers.delete("Content-Encoding");
  return new Response(JSON.stringify(payload), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function installCompactFetchGuard() {
  if (typeof window === "undefined") return false;
  const guarded = window as CompactWindow;
  if (guarded.__pdpCompactFetchInstalled) return true;
  if (!guarded.__pdpPaginationNativeFetch) return false;

  const innerFetch = window.fetch.bind(window);
  guarded.__pdpCompactFetchInstalled = true;
  guarded.__pdpCompactInnerFetch = innerFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return innerFetch(input, init);
    let original: URL;
    try {
      original = new URL(requestUrl(input), window.location.origin);
    } catch {
      return innerFetch(input, init);
    }

    const top = activeTopTab();
    const workflowLabel = activeWorkflow();
    const noticeTab = top === "مناقصات" || top === "استعلامات";
    const isNoticeCollection = original.origin === window.location.origin &&
      (original.pathname === NOTICE_PATH || original.pathname === RECOMMENDED_PATH);
    if (!noticeTab || !isNoticeCollection) return innerFetch(input, init);

    const forceRecommended = original.pathname === RECOMMENDED_PATH;
    const params = buildCompactQuery(forceRecommended);
    const workflow = workflowCode(workflowLabel, forceRecommended);
    const contextKey = JSON.stringify([top, workflowLabel, ...Array.from(params.entries())]);

    guarded.__pdpCompactAbortController?.abort();
    const controller = new AbortController();
    guarded.__pdpCompactAbortController = controller;
    const requestInit: RequestInit = { ...init, signal: controller.signal };
    const response = await innerFetch(`${COMPACT_NOTICE_PATH}?${params.toString()}`, requestInit);
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;

    const payload = await response.clone().json() as NoticePayload;
    const normalizedPayload = normalizeCompactPayload(payload, workflow);
    const current = currentUiState();
    if (!controller.signal.aborted && current.top === top && current.workflow === workflowLabel) {
      window.dispatchEvent(new CustomEvent(DATA_EVENT, { detail: normalizedPayload }));
      window.dispatchEvent(new CustomEvent(PAGINATION_META_EVENT, { detail: {
        count: Number(normalizedPayload.count || 0),
        page: Number(normalizedPayload.page || 1),
        pageSize: Number(normalizedPayload.page_size || 50),
        contextKey,
        top,
        workflow: workflowLabel,
      } }));
    }
    return jsonResponse(response, normalizedPayload);
  };
  return true;
}

function ensureFilterHost() {
  const top = activeTopTab();
  if (top !== "مناقصات" && top !== "استعلامات") return null;
  const section = findWorkflowSection();
  if (!section) return null;
  const searchLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) =>
    normalize(label.textContent).startsWith("جست‌وجو"),
  );
  const bar = searchLabel?.parentElement;
  if (!bar) return null;
  let host = bar.querySelector<HTMLElement>(`#${FILTER_HOST_ID}`);
  if (!host) {
    host = document.createElement("div");
    host.id = FILTER_HOST_ID;
    host.style.display = "contents";
    bar.appendChild(host);
  }
  return host;
}

function ensureDashboardHost() {
  if (activeTopTab() !== "داشبورد مدیریتی") return null;
  const kpiArticle = Array.from(document.querySelectorAll<HTMLElement>("article")).find((article) =>
    Array.from(article.querySelectorAll("span")).some((span) => normalize(span.textContent) === "فراخوان جدید"),
  );
  const kpiContainer = kpiArticle?.parentElement as HTMLElement | null;
  if (!kpiContainer) return null;
  if (kpiContainer.style.display !== "none") kpiContainer.style.display = "none";
  const dashboardSection = kpiContainer.closest("section");
  if (!dashboardSection) return null;
  const alertHeading = Array.from(dashboardSection.querySelectorAll("h2")).find((heading) => normalize(heading.textContent) === "هشدارهای مدیریتی");
  const oldGrid = alertHeading?.closest("article")?.parentElement as HTMLElement | null;
  if (oldGrid && oldGrid.style.display !== "none") oldGrid.style.display = "none";
  let host = dashboardSection.querySelector<HTMLElement>(`#${DASHBOARD_HOST_ID}`);
  if (!host) {
    host = document.createElement("div");
    host.id = DASHBOARD_HOST_ID;
    dashboardSection.insertBefore(host, kpiContainer);
  }
  return host;
}

function hideLiveDatabaseBanner() {
  const label = Array.from(document.querySelectorAll("b")).find((node) => normalize(node.textContent) === "داده واقعی");
  const banner = label?.parentElement as HTMLElement | null;
  if (banner && normalize(banner.textContent).includes("PostgreSQL") && banner.style.display !== "none") {
    banner.style.display = "none";
  }
}

function ensureSourceOptions(sourceNames: string[]) {
  const section = findWorkflowSection();
  if (!section) return;
  const sourceLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("منبع"));
  const select = sourceLabel?.querySelector<HTMLSelectElement>("select");
  if (!select) return;
  const existing = new Set(Array.from(select.options).map((option) => option.value));
  sourceNames.forEach((name) => {
    if (!name || existing.has(name)) return;
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
    existing.add(name);
  });
}

function deadlineInfo(value: string | null) {
  if (!value) return { remaining: "مهلت نامشخص", date: "مهلت: نامشخص" };
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return { remaining: "مهلت نامشخص", date: `مهلت: ${value}` };
  const hours = Math.ceil((parsed.getTime() - Date.now()) / 3600000);
  const remaining = hours < 0
    ? `${fa.format(Math.ceil(Math.abs(hours) / 24))} روز از مهلت گذشته`
    : hours < 24
      ? `${fa.format(hours)} ساعت باقی‌مانده`
      : `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`;
  return { remaining, date: `مهلت: ${faDate.format(parsed)}` };
}

function chip(text: string, className = "") {
  const element = document.createElement("span");
  element.className = `pdp-compact-chip ${className}`.trim();
  element.textContent = text;
  return element;
}

function recordBadgeSignature(item: CompactNotice) {
  const deadline = deadlineInfo(item.submission_deadline);
  const sources = [...item.sources].sort(sourceSort).map((source) => [source.name, source.detail_url || source.source_url]);
  return JSON.stringify([sources, item.province, deadline.remaining, deadline.date]);
}

function enhanceRecordCards(payload: NoticePayload | null) {
  const top = activeTopTab();
  if (!new Set(["مناقصات", "استعلامات", "ارجاعات مستقیم"]).has(top)) return;
  const section = findWorkflowSection();
  if (!section) return;
  const records = Array.from(section.querySelectorAll<HTMLElement>("article")).filter((article) => Boolean(article.querySelector("h3")));
  records.forEach((article) => article.classList.add("pdp-compact-record"));

  if ((top === "مناقصات" || top === "استعلامات") && payload) {
    records.slice(0, payload.results.length).forEach((article, index) => {
      const item = payload.results[index];
      const heading = article.querySelector("h3");
      const content = heading?.parentElement as HTMLElement | null;
      const recordTop = content?.firstElementChild as HTMLElement | null;
      const cluster = recordTop?.lastElementChild instanceof HTMLElement ? recordTop.lastElementChild : null;
      if (!cluster || !item) return;

      const sourceNames = new Set(item.sources.map((source) => normalize(source.name)));
      cluster.querySelectorAll<HTMLAnchorElement>("a").forEach((anchor) => {
        if (sourceNames.has(normalize(anchor.textContent)) && anchor.style.display !== "none") anchor.style.display = "none";
      });

      const signature = recordBadgeSignature(item);
      const existingGroup = cluster.querySelector<HTMLElement>("[data-pdp-compact-badges]");
      if (!existingGroup || existingGroup.dataset.pdpCompactSignature !== signature) {
        existingGroup?.remove();
        const group = document.createElement("div");
        group.dataset.pdpCompactBadges = "true";
        group.dataset.pdpCompactSignature = signature;
        group.className = "pdp-compact-badge-group";
        [...item.sources].sort(sourceSort).forEach((source) => {
          const anchor = document.createElement("a");
          anchor.href = source.detail_url || source.source_url;
          anchor.target = "_blank";
          anchor.rel = "noreferrer";
          anchor.textContent = source.name;
          anchor.className = `pdp-compact-source pdp-source-${sourceRank(source.name)}`;
          group.appendChild(anchor);
        });
        if (item.sources.length > 1) group.appendChild(chip(`${fa.format(item.sources.length)} منبع`, "pdp-source-count"));
        if (item.province) group.appendChild(chip(item.province));
        const deadline = deadlineInfo(item.submission_deadline);
        group.appendChild(chip(deadline.remaining));
        group.appendChild(chip(deadline.date, "pdp-deadline-date"));
        cluster.insertBefore(group, cluster.firstChild);
      }

      const facts = Array.from(content?.querySelectorAll<HTMLElement>("div") || []).find((candidate) =>
        Array.from(candidate.children).some((child) => normalize(child.textContent).startsWith("پردازش:")),
      );
      if (facts) {
        Array.from(facts.children).forEach((child) => {
          const text = normalize(child.textContent);
          if (text.startsWith("پردازش:") || text === item.province || text.includes("باقی‌مانده") || text.includes("از مهلت گذشته")) {
            const element = child as HTMLElement;
            if (element.style.display !== "none") element.style.display = "none";
          }
        });
        const visible = Array.from(facts.children).some((child) => (child as HTMLElement).style.display !== "none");
        if (!visible && facts.style.display !== "none") facts.style.display = "none";
      }
    });
  }

  records.forEach((article) => {
    const dismiss = Array.from(article.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === "حذف از پیشنهادی");
    if (!dismiss) return;
    dismiss.classList.add("pdp-compact-dismiss");
    const select = Array.from(article.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === "انتخاب");
    const dismissHost = dismiss.parentElement as HTMLElement | null;
    const actions = select?.parentElement as HTMLElement | null;
    if (dismissHost && dismissHost.style.marginTop !== "0px") dismissHost.style.marginTop = "0";
    if (actions && dismissHost && dismissHost.parentElement !== actions) {
      actions.appendChild(dismissHost);
      actions.classList.add("pdp-compact-row-actions");
    }
  });
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function DashboardBox({ data }: { data: DashboardPayload }) {
  const metrics: Array<[string, CountBreakdown]> = [
    ["کل فراخوان‌ها", data.metrics.all_notices],
    ["فراخوان جدید امروز", data.metrics.new_today],
    ["تحلیل‌نشده", data.metrics.analysis_remaining],
    ["پیشنهادی", data.metrics.recommended],
    ["منتخب", data.metrics.selected],
    ["ارسال‌شده", data.metrics.submitted],
    ["مهلت تا ۷ روز", data.metrics.near_deadline],
    ["نتیجه موفق", data.metrics.successful_results],
  ];
  const analysisLabel = data.analysis.basis === "active_run_remaining" ? "بر اساس صف واقعی Run فعال تحلیل" : "بر اساس فراخوان‌های فاقد پیش‌نویس تحلیل";
  return <article dir="rtl" className="pdp-compact-dashboard-box">
    <div className="pdp-compact-dashboard-heading">
      <div><h2>شاخص‌های مدیریتی</h2><small>محاسبه مستقیم سمت سرور؛ تفکیک مناقصه و استعلام</small></div>
      <small>{faDateTime.format(new Date(data.generated_at))}</small>
    </div>
    <div className="pdp-compact-dashboard-metrics">
      {metrics.map(([label, value]) => <div className="pdp-compact-metric" key={label}>
        <span>{label}</span><b>{fa.format(value.total || 0)}</b>
        <small><em>مناقصه {fa.format(value.tender || 0)}</em><em>استعلام {fa.format(value.inquiry || 0)}</em></small>
      </div>)}
    </div>
    <div className="pdp-compact-dashboard-foot">
      <span>تحلیل‌نشده: {analysisLabel}</span>
      <span>پیگیری عقب‌افتاده: <b>{fa.format(data.management.overdue_actions || 0)}</b></span>
      <span>بدون مسئول: <b>{fa.format(data.management.without_responsible || 0)}</b></span>
      <span>ارجاع مستقیم فعال: <b>{fa.format(data.management.direct_active || 0)}</b></span>
    </div>
  </article>;
}

export default function ProcurementCompactWorkspaceStableEnhancement() {
  const [noticePayload, setNoticePayload] = useState<NoticePayload | null>(null);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [filterHost, setFilterHost] = useState<HTMLElement | null>(null);
  const [dashboardHost, setDashboardHost] = useState<HTMLElement | null>(null);
  const [deadlineStatus, setDeadlineStatus] = useState("");
  const [publishedOn, setPublishedOn] = useState("");
  const [bulkScope, setBulkScope] = useState<"page" | "all">("page");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [sourceNames, setSourceNames] = useState<string[]>([]);
  const [uiState, setUiState] = useState<UiState>({ top: "", workflow: "" });
  const previousTop = useRef("");
  const dashboardLoading = useRef(false);
  const dashboardLoadedAt = useRef(0);

  const refreshDashboard = useCallback((force = false) => {
    if (activeTopTab() !== "داشبورد مدیریتی") return;
    if (dashboardLoading.current) return;
    if (!force && dashboardLoadedAt.current && Date.now() - dashboardLoadedAt.current < DASHBOARD_TTL_MS) return;
    dashboardLoading.current = true;
    void fetch(COMPACT_DASHBOARD_PATH, { credentials: "include", headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error("dashboard");
        return response.json() as Promise<DashboardPayload>;
      })
      .then((payload) => {
        dashboardLoadedAt.current = Date.now();
        setDashboard(payload);
      })
      .catch(() => setMessage("به‌روزرسانی شاخص‌های مدیریتی موقتاً انجام نشد."))
      .finally(() => { dashboardLoading.current = false; });
  }, []);

  useEffect(() => {
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (installCompactFetchGuard() || attempts > 40) window.clearInterval(timer);
    }, 50);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleData = (event: Event) => setNoticePayload((event as CustomEvent<NoticePayload>).detail || null);
    window.addEventListener(DATA_EVENT, handleData);
    return () => window.removeEventListener(DATA_EVENT, handleData);
  }, []);

  useEffect(() => {
    void fetch(`${PROCUREMENT_API}/sources/?page_size=100`, { credentials: "include", headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() as Promise<SourcePayload> : Promise.reject(new Error("sources")))
      .then((payload) => {
        const items = Array.isArray(payload) ? payload : payload.results || [];
        setSourceNames(items.map((item) => item.name).filter(Boolean).sort((a, b) => sourceRank(a) - sourceRank(b) || a.localeCompare(b, "fa")));
      })
      .catch(() => setSourceNames([]));
  }, []);

  useEffect(() => {
    const guarded = window as CompactWindow;
    guarded.__pdpCompactDeadlineStatus = deadlineStatus;
    guarded.__pdpCompactPublishedOn = publishedOn;
  }, [deadlineStatus, publishedOn]);

  useEffect(() => {
    let syncFrame = 0;
    let clickFrame = 0;

    const syncDom = () => {
      hideLiveDatabaseBanner();
      const nextState = currentUiState();
      synchronizeCompactTop(nextState.top);
      if (previousTop.current && previousTop.current !== nextState.top) {
        setDeadlineStatus("");
        setPublishedOn("");
      }
      previousTop.current = nextState.top;
      setUiState((current) => current.top === nextState.top && current.workflow === nextState.workflow ? current : nextState);

      const nextFilterHost = ensureFilterHost();
      setFilterHost((current) => current === nextFilterHost ? current : nextFilterHost);
      const nextDashboardHost = ensureDashboardHost();
      setDashboardHost((current) => current === nextDashboardHost ? current : nextDashboardHost);
      ensureSourceOptions(sourceNames);
      enhanceRecordCards(noticePayload);
      if (nextState.top === "داشبورد مدیریتی") refreshDashboard(false);
    };

    const scheduleSync = () => {
      if (syncFrame) return;
      syncFrame = window.requestAnimationFrame(() => {
        syncFrame = 0;
        syncDom();
      });
    };

    const onClick = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      const label = normalize(button?.textContent);
      if (!TOP_LABELS.has(label) && !WORKFLOW_LABELS.has(label)) return;
      window.cancelAnimationFrame(clickFrame);
      clickFrame = window.requestAnimationFrame(scheduleSync);
    };

    scheduleSync();
    const observer = new MutationObserver(scheduleSync);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", onClick, true);
    return () => {
      observer.disconnect();
      document.removeEventListener("click", onClick, true);
      window.cancelAnimationFrame(syncFrame);
      window.cancelAnimationFrame(clickFrame);
    };
  }, [noticePayload, sourceNames, refreshDashboard]);

  useEffect(() => {
    const handleSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (detail?.source === "compact-workspace") return;
      if (detail?.dashboard || detail?.bulkWorkspace) refreshDashboard(true);
      else if (activeTopTab() === "داشبورد مدیریتی") refreshDashboard(false);
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
  }, [refreshDashboard]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      if (normalize(button?.textContent) !== "پاک‌کردن") return;
      if (!button?.closest("section")) return;
      setDeadlineStatus("");
      setPublishedOn("");
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  const triggerFilterRefresh = useCallback((nextDeadline: string, nextDate: string) => {
    const guarded = window as CompactWindow;
    guarded.__pdpCompactDeadlineStatus = nextDeadline;
    guarded.__pdpCompactPublishedOn = nextDate;
    guarded.__pdpPaginationPage = 1;
    emitProcurementUiSync({ source: "compact-workspace", bulkWorkspace: true });
  }, []);

  const bulkDismiss = useCallback(async () => {
    const top = activeTopTab();
    if ((top !== "مناقصات" && top !== "استعلامات") || activeWorkflow() !== "پیشنهادی" || !noticePayload) return;
    const count = bulkScope === "page" ? noticePayload.results.length : noticePayload.count;
    if (!count) return;
    const scopeText = bulkScope === "page" ? "پیشنهادهای همین صفحه" : "همه پیشنهادهای مطابق فیلتر فعلی";
    if (!window.confirm(`${scopeText} (${fa.format(count)} مورد) از فهرست پیشنهادی حذف شوند؟ خود فراخوان‌ها و سابقه تحلیل حذف نمی‌شوند.`)) return;
    setBulkBusy(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const params = buildCompactQuery(true);
      params.delete("page");
      params.delete("page_size");
      const body = bulkScope === "all"
        ? { dismiss_all: true, reason: "حذف گروهی از فهرست پیشنهادی توسط کاربر" }
        : { notice_ids: noticePayload.results.map((item) => item.id), reason: "حذف گروهی از صفحه جاری فهرست پیشنهادی توسط کاربر" };
      const response = await fetch(`${BULK_DISMISS_PATH}?${params.toString()}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json() as { dismissed?: number; detail?: string };
      if (!response.ok) throw new Error(payload.detail || "حذف گروهی پیشنهادها انجام نشد.");
      setMessage(`${fa.format(payload.dismissed || 0)} پیشنهاد از فهرست پیشنهادی حذف شد؛ فراخوان‌ها و سابقه تحلیل حفظ شدند.`);
      emitProcurementUiSync({ source: "compact-workspace", bulkWorkspace: true, dashboard: true });
      refreshDashboard(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "حذف گروهی پیشنهادها انجام نشد.");
    } finally {
      setBulkBusy(false);
    }
  }, [bulkScope, noticePayload, refreshDashboard]);

  const showBulk = (uiState.top === "مناقصات" || uiState.top === "استعلامات") && uiState.workflow === "پیشنهادی";
  const filterPortal = filterHost ? createPortal(<>
    <label className="pdp-compact-filter-label">وضعیت مهلت
      <select value={deadlineStatus} onChange={(event) => {
        const value = event.target.value;
        setDeadlineStatus(value);
        triggerFilterRefresh(value, publishedOn);
      }}>
        <option value="">همه وضعیت‌ها</option>
        <option value="expired">منقضی شده</option>
        <option value="expiring">در حال انقضا (تا ۳ روز)</option>
        <option value="available">فرصت دارد</option>
        <option value="unknown">مهلت نامشخص</option>
      </select>
    </label>
    <label className="pdp-compact-filter-label">تاریخ انتشار
      <input type="date" value={publishedOn} onChange={(event) => {
        const value = event.target.value;
        setPublishedOn(value);
        triggerFilterRefresh(deadlineStatus, value);
      }} />
    </label>
    {showBulk && <div className="pdp-compact-bulk-control">
      <select value={bulkScope} onChange={(event) => setBulkScope(event.target.value as "page" | "all")}>
        <option value="page">همین صفحه</option>
        <option value="all">همه نتایج فیلترشده</option>
      </select>
      <button type="button" disabled={bulkBusy || !noticePayload?.count} onClick={() => void bulkDismiss()}>{bulkBusy ? "در حال حذف..." : "حذف گروهی پیشنهادها"}</button>
    </div>}
    {message && <small className="pdp-compact-message">{message}</small>}
  </>, filterHost) : null;

  const dashboardPortal = dashboardHost && dashboard ? createPortal(<DashboardBox data={dashboard} />, dashboardHost) : null;

  return <>
    <style>{`
      .pdp-compact-record{padding:6px 9px!important;gap:6px!important;grid-template-columns:minmax(0,1fr) minmax(145px,.23fr)!important;min-height:0!important}
      .pdp-compact-record h3{font-size:15px!important;line-height:1.5!important;margin:2px 0 1px!important}
      .pdp-compact-record p{font-size:12px!important;line-height:1.45!important;margin:1px 0!important}
      .pdp-compact-record>div:last-child{gap:4px!important;padding-inline-start:7px!important}
      .pdp-compact-badge-group{display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap}
      .pdp-compact-source,.pdp-compact-chip{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border-radius:999px;border:1px solid #cbd5e1;background:#f8fafc;color:#334155;font-size:10.5px;font-weight:700;text-decoration:none;white-space:nowrap}
      .pdp-source-0{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.pdp-source-1{border-color:#bfdbfe;background:#eff6ff;color:#1d4ed8}.pdp-source-2{border-color:#fde68a;background:#fffbeb;color:#a16207}
      .pdp-source-count{background:#f1f5f9}.pdp-deadline-date{background:#fff7ed;border-color:#fed7aa;color:#9a3412}
      .pdp-compact-dismiss{width:auto!important;min-height:28px!important;padding:4px 7px!important;font-size:10.5px!important}
      .pdp-compact-row-actions{display:flex!important;align-items:center!important;gap:5px!important;flex-wrap:wrap!important}
      .pdp-compact-filter-label{display:grid;gap:3px;font-size:11px}.pdp-compact-filter-label select,.pdp-compact-filter-label input{width:100%;min-height:34px;border:1px solid rgba(15,23,42,.16);border-radius:8px;padding:5px 7px;background:white;font:inherit}
      .pdp-compact-bulk-control{display:flex;align-items:end;gap:5px;align-self:end}.pdp-compact-bulk-control select,.pdp-compact-bulk-control button{min-height:34px;border:1px solid #cbd5e1;border-radius:8px;background:white;padding:5px 7px;font:inherit;font-size:11px}.pdp-compact-bulk-control button{border-color:#fecaca;background:#fff1f2;color:#be123c;font-weight:700;cursor:pointer}.pdp-compact-bulk-control button:disabled{opacity:.5;cursor:not-allowed}
      .pdp-compact-message{align-self:end;color:#0f766e;font-weight:700;grid-column:1/-1}
      .pdp-compact-dashboard-box{background:white;border:1px solid #dbe3ec;border-radius:14px;padding:12px;margin-bottom:12px;box-shadow:0 4px 14px rgba(15,23,42,.04)}
      .pdp-compact-dashboard-heading{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px;flex-wrap:wrap}.pdp-compact-dashboard-heading h2{font-size:17px;margin:0 0 2px}.pdp-compact-dashboard-heading small{color:#64748b;font-size:10.5px}
      .pdp-compact-dashboard-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.pdp-compact-metric{border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:8px 9px;min-height:74px}.pdp-compact-metric>span{display:block;color:#64748b;font-size:10.5px}.pdp-compact-metric>b{display:block;font-size:20px;line-height:1.25;margin:3px 0}.pdp-compact-metric small{display:flex;gap:4px;flex-wrap:wrap}.pdp-compact-metric em{font-style:normal;font-size:9.5px;background:white;border:1px solid #e2e8f0;border-radius:999px;padding:1px 5px}
      .pdp-compact-dashboard-foot{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;color:#475569;font-size:10.5px}.pdp-compact-dashboard-foot span{background:#f8fafc;border-radius:999px;padding:3px 7px}
      @media(max-width:900px){.pdp-compact-dashboard-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.pdp-compact-record{grid-template-columns:1fr!important}.pdp-compact-record>div:last-child{border-inline-start:0!important;border-top:1px solid #e2e8f0!important;padding-top:5px!important}}
    `}</style>
    {filterPortal}
    {dashboardPortal}
  </>;
}
