"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT } from "./procurementUiSync";

type DeadlineState = "" | "expired" | "expiring" | "available" | "unknown";
type CompactFilters = { deadlineState: DeadlineState; publishedOn: string };
type SourceBadge = { name: string; url: string };
type NoticeRow = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  published_date: string | null;
  submission_deadline: string | null;
  source_count?: number;
  source_name: string;
  source_url: string;
  detail_url: string;
};
type NoticeDetail = NoticeRow & {
  source_links?: Array<{
    source_notice?: {
      source_name?: string;
      source_url?: string;
      detail_url?: string;
    };
  }>;
};
type RowPresentation = NoticeRow & { sources: SourceBadge[] };
type Collection<T> = T[] | { count?: number; next?: string | null; previous?: string | null; results?: T[] };
type Breakdown = { total: number; tender: number; inquiry: number };
type DashboardMetrics = {
  breakdown?: Record<string, Breakdown>;
  analysis_basis?: string;
  analysis_run_id?: string | null;
  direct?: { active?: number; recommended?: number; selected?: number; submitted?: number; won?: number; lost?: number };
};
type CompactWindow = Window & {
  __pdpCompactBrowseInstalled?: boolean;
  __pdpCompactFilters?: CompactFilters;
  __pdpPaginationNativeFetch?: typeof window.fetch;
  __pdpPaginationPage?: number;
  __pdpPaginationPageSize?: number;
};

const API_PREFIX = "/api/v1/procurement/";
const NOTICE_PATH = `${API_PREFIX}notices/`;
const RECOMMENDED_PATH = `${API_PREFIX}recommended-notices/`;
const BROWSE_NOTICE_PATH = `${API_PREFIX}browse-notices/`;
const BROWSE_RECOMMENDED_PATH = `${API_PREFIX}browse-recommended-notices/`;
const METRICS_PATH = `${API_PREFIX}pagination-dashboard-metrics/`;
const FILTER_HOST_ID = "pdp-compact-workflow-filter-host";
const DASHBOARD_HOST_ID = "pdp-compact-dashboard-summary-host";
const PAGINATION_META_EVENT = "pdp-procurement-pagination-meta";
const TOP_NOTICE_LABELS = new Set(["مناقصات", "استعلامات"]);
const WORKFLOW_LABELS = new Set([
  "مناقصات ۳ روز اخیر", "استعلامات ۳ روز اخیر", "پیشنهادی", "منتخب", "ارسال‌شده", "نتایج",
]);
const fa = new Intl.NumberFormat("fa-IR");
const persianDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" });

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeEmployer(value: string | null | undefined) {
  const normalized = normalize(value);
  return normalized === "کارفرما نامشخص" ? "" : normalized;
}

function rowKey(title: string, employer: string) {
  return `${normalize(title)}\u0000${normalizeEmployer(employer)}`;
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function rewrittenInput(input: RequestInfo | URL, url: URL): RequestInfo | URL {
  if (input instanceof Request) return new Request(url.toString(), input);
  if (input instanceof URL) return url;
  return `${url.pathname}${url.search}`;
}

function activeTopLabel() {
  const nav = document.querySelector("main[dir='rtl'] nav");
  const button = Array.from(nav?.querySelectorAll<HTMLButtonElement>("button") || []).find((candidate) =>
    Boolean(normalize(candidate.className)) && ["داشبورد مدیریتی", "مناقصات", "استعلامات", "ارجاعات مستقیم", "مدیریت زیرسامانه"].includes(normalize(candidate.textContent)),
  );
  return normalize(button?.textContent);
}

function activeWorkflowLabel() {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((candidate) =>
    WORKFLOW_LABELS.has(normalize(candidate.textContent)) && Boolean(normalize(candidate.className)),
  );
  return normalize(button?.textContent);
}

function fieldValue(prefix: string) {
  const label = Array.from(document.querySelectorAll<HTMLLabelElement>("label")).find((candidate) =>
    normalize(candidate.textContent).startsWith(prefix),
  );
  return normalize(label?.querySelector<HTMLInputElement | HTMLSelectElement>("input,select")?.value);
}

function currentPageState() {
  const guarded = window as CompactWindow;
  return {
    page: Math.max(1, Number(guarded.__pdpPaginationPage || 1)),
    pageSize: Math.max(1, Number(guarded.__pdpPaginationPageSize || 50)),
  };
}

function addExistingFilters(url: URL) {
  const search = fieldValue("جست‌وجو");
  const source = fieldValue("منبع");
  const province = fieldValue("استان");
  const importance = fieldValue("اهمیت");
  const urgency = fieldValue("فوریت");
  if (search) url.searchParams.set("search", search);
  if (source) url.searchParams.set("source_name", source);
  if (province) url.searchParams.set("province", province);
  if (importance) url.searchParams.set("importance", importance);
  if (urgency) url.searchParams.set("urgency", urgency);
}

function buildBrowseUrl(top: string, workflow: string, filters: CompactFilters) {
  const recommended = workflow === "پیشنهادی";
  const url = new URL(recommended ? BROWSE_RECOMMENDED_PATH : BROWSE_NOTICE_PATH, window.location.origin);
  url.searchParams.set("resolved_notice_type", top === "مناقصات" ? "tender" : "inquiry");
  url.searchParams.set("ordering", "-publication_sort,-last_seen_at,-id");
  if (workflow === "مناقصات ۳ روز اخیر" || workflow === "استعلامات ۳ روز اخیر") url.searchParams.set("recent_days", "3");
  else if (workflow === "پیشنهادی") url.searchParams.set("actionable", "true");
  else if (workflow === "منتخب") url.searchParams.set("workflow_view", "selected");
  else if (workflow === "ارسال‌شده") url.searchParams.set("workflow_view", "submitted");
  else if (workflow === "نتایج") url.searchParams.set("workflow_view", "results");
  addExistingFilters(url);
  if (filters.deadlineState) url.searchParams.set("deadline_state", filters.deadlineState);
  if (filters.publishedOn) url.searchParams.set("published_on", filters.publishedOn);
  const page = currentPageState();
  url.searchParams.set("page", String(page.page));
  url.searchParams.set("page_size", String(page.pageSize));
  return url;
}

function jsonResponse(response: Response, payload: unknown) {
  const headers = new Headers(response.headers);
  headers.set("Content-Type", "application/json");
  headers.delete("Content-Length");
  headers.delete("Content-Encoding");
  return new Response(JSON.stringify(payload), { status: response.status, statusText: response.statusText, headers });
}

function installCompactBrowseFetch() {
  if (typeof window === "undefined") return;
  const guarded = window as CompactWindow;
  if (guarded.__pdpCompactBrowseInstalled) return;
  guarded.__pdpCompactBrowseInstalled = true;
  guarded.__pdpCompactFilters = guarded.__pdpCompactFilters || { deadlineState: "", publishedOn: "" };
  const innerFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return innerFetch(input, init);
    let original: URL;
    try {
      original = new URL(requestUrl(input), window.location.origin);
    } catch {
      return innerFetch(input, init);
    }
    if (original.origin !== window.location.origin || ![NOTICE_PATH, RECOMMENDED_PATH].includes(original.pathname)) return innerFetch(input, init);

    const filters = guarded.__pdpCompactFilters || { deadlineState: "", publishedOn: "" };
    if (!filters.deadlineState && !filters.publishedOn) return innerFetch(input, init);
    const top = activeTopLabel();
    if (!TOP_NOTICE_LABELS.has(top)) return innerFetch(input, init);
    const workflow = activeWorkflowLabel();
    const nextUrl = buildBrowseUrl(top, workflow, filters);
    const nativeFetch = guarded.__pdpPaginationNativeFetch || innerFetch;
    const response = await nativeFetch(rewrittenInput(input, nextUrl), init);
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
    try {
      const payload = await response.clone().json() as Collection<unknown>;
      if (!Array.isArray(payload) && Array.isArray(payload.results)) {
        const page = currentPageState();
        const contextKey = JSON.stringify([top, workflow, fieldValue("جست‌وجو"), fieldValue("منبع"), fieldValue("استان"), fieldValue("اهمیت"), fieldValue("فوریت"), filters.deadlineState, filters.publishedOn]);
        window.dispatchEvent(new CustomEvent(PAGINATION_META_EVENT, { detail: {
          count: Number(payload.count || 0), page: page.page, pageSize: page.pageSize, contextKey,
        } }));
        return jsonResponse(response, { ...payload, next: null, previous: null });
      }
    } catch {
      return response;
    }
    return response;
  };
}

function sourceRank(name: string) {
  const value = normalize(name).toLowerCase();
  if (value.includes("ستاد")) return 1;
  if (value.includes("هزاره")) return 2;
  if (value.includes("پارس") && value.includes("نماد")) return 3;
  return 10;
}

function orderedSources(sources: SourceBadge[]) {
  const unique = new Map<string, SourceBadge>();
  for (const source of sources) {
    const key = normalize(source.name);
    if (key && !unique.has(key)) unique.set(key, source);
  }
  return Array.from(unique.values()).sort((a, b) => {
    const rank = sourceRank(a.name) - sourceRank(b.name);
    return rank || a.name.localeCompare(b.name, "fa");
  });
}

function formatDeadline(value: string | null) {
  if (!value) return "مهلت نامشخص";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `مهلت: ${value}`;
  return `مهلت: ${persianDate.format(date)}`;
}

function remainingLabel(value: string | null) {
  if (!value) return "زمان نامشخص";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return "زمان نامشخص";
  const hours = Math.ceil((time - Date.now()) / 3600000);
  if (hours < 0) return `${fa.format(Math.ceil(Math.abs(hours) / 24))} روز از مهلت گذشته`;
  if (hours < 24) return `${fa.format(hours)} ساعت باقی‌مانده`;
  return `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`;
}

function sourceBadgeStyle() {
  return "display:inline-flex;align-items:center;min-height:21px;padding:2px 7px;border-radius:999px;border:1px solid rgba(15,118,110,.22);background:#ecfdf5;color:#0f766e;font-size:10.5px;font-weight:700;text-decoration:none;white-space:nowrap";
}

function metaBadgeStyle() {
  return "display:inline-flex;align-items:center;min-height:21px;padding:2px 7px;border-radius:999px;border:1px solid #e2e8f0;background:#f8fafc;color:#475569;font-size:10.5px;font-weight:600;white-space:nowrap";
}

function patchTitle(h3: HTMLElement) {
  h3.style.whiteSpace = "normal";
  h3.style.textOverflow = "clip";
  h3.style.lineHeight = "1.65";
  h3.style.maxWidth = "100%";
  const length = normalize(h3.textContent).length;
  if (length > 220) {
    h3.style.display = "-webkit-box";
    h3.style.overflow = "hidden";
    h3.style.setProperty("-webkit-box-orient", "vertical");
    h3.style.setProperty("-webkit-line-clamp", "2");
  } else {
    h3.style.display = "block";
    h3.style.overflow = "visible";
    h3.style.removeProperty("-webkit-box-orient");
    h3.style.removeProperty("-webkit-line-clamp");
  }
}

function patchNoticeRows(rows: Map<string, RowPresentation>) {
  const top = activeTopLabel();
  const main = document.querySelector<HTMLElement>("main[dir='rtl']");
  if (!main) return;

  const directMode = top === "ارجاعات مستقیم";
  if (!TOP_NOTICE_LABELS.has(top) && !directMode) return;
  main.querySelectorAll<HTMLElement>("article").forEach((article) => {
    const h3 = article.querySelector<HTMLElement>("h3");
    if (!h3) return;
    if (!article.querySelector<HTMLButtonElement>("button")) return;
    patchTitle(h3);
    article.style.padding = "7px 10px";
    article.style.gap = "7px";
    article.style.minHeight = "0";
    article.style.alignItems = "start";
    article.style.gridTemplateColumns = "minmax(0,1fr) minmax(175px,220px)";

    if (directMode) return;
    const content = h3.parentElement as HTMLElement | null;
    const employer = normalizeEmployer(content?.querySelector("p")?.textContent);
    const row = rows.get(rowKey(h3.textContent || "", employer));
    if (!content || !row) return;

    const topRow = Array.from(content.children).find((node) => node instanceof HTMLElement && node.tagName === "DIV") as HTMLElement | undefined;
    if (!topRow) return;
    const badgeTarget = Array.from(topRow.querySelectorAll<HTMLElement>("div")).find((candidate) =>
      Array.from(candidate.querySelectorAll("button")).some((button) => normalize(button.textContent) === "مشاهده"),
    ) || topRow;

    topRow.querySelectorAll<HTMLAnchorElement>("a").forEach((anchor) => { anchor.style.display = "none"; });
    let sourceHost = badgeTarget.querySelector<HTMLElement>("[data-pdp-compact-source-badges]");
    if (!sourceHost) {
      sourceHost = document.createElement("span");
      sourceHost.dataset.pdpCompactSourceBadges = "true";
      sourceHost.style.cssText = "display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap";
      badgeTarget.prepend(sourceHost);
    }
    sourceHost.replaceChildren();
    row.sources.forEach((source) => {
      const anchor = document.createElement("a");
      anchor.href = source.url || "#";
      anchor.target = "_blank";
      anchor.rel = "noreferrer";
      anchor.textContent = source.name;
      anchor.style.cssText = sourceBadgeStyle();
      sourceHost?.appendChild(anchor);
    });

    let metaHost = badgeTarget.querySelector<HTMLElement>("[data-pdp-compact-meta-badges]");
    if (!metaHost) {
      metaHost = document.createElement("span");
      metaHost.dataset.pdpCompactMetaBadges = "true";
      metaHost.style.cssText = "display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap";
      sourceHost.after(metaHost);
    }
    metaHost.replaceChildren();
    const meta = [row.province, remainingLabel(row.submission_deadline), formatDeadline(row.submission_deadline)].filter(Boolean);
    meta.forEach((label) => {
      const span = document.createElement("span");
      span.textContent = label;
      span.style.cssText = metaBadgeStyle();
      metaHost?.appendChild(span);
    });

    content.querySelectorAll<HTMLElement>("span").forEach((span) => {
      if (span.closest("[data-pdp-compact-source-badges],[data-pdp-compact-meta-badges]")) return;
      const text = normalize(span.textContent);
      if (text.startsWith("پردازش:") || text === normalize(row.province) || text.includes("باقی‌مانده") || text.includes("از مهلت گذشته")) {
        span.style.display = "none";
      }
    });

    const dismiss = Array.from(article.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === "حذف از پیشنهادی");
    const select = Array.from(article.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === "انتخاب");
    if (dismiss) {
      dismiss.style.width = "auto";
      dismiss.style.minHeight = "28px";
      dismiss.style.padding = "4px 8px";
      dismiss.style.fontSize = "10.5px";
      dismiss.style.borderRadius = "7px";
      if (select?.parentElement && dismiss.parentElement !== select.parentElement) select.parentElement.appendChild(dismiss);
      if (select?.parentElement) {
        select.parentElement.style.display = "flex";
        select.parentElement.style.gap = "5px";
        select.parentElement.style.flexWrap = "wrap";
      }
    }
  });
}

async function csrfToken() {
  const response = await fetch("/api/v1/auth/session/", { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function yesterdayIso() {
  const value = new Date();
  value.setDate(value.getDate() - 1);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function DashboardSummary({ metrics }: { metrics: DashboardMetrics }) {
  const breakdown = metrics.breakdown || {};
  const cells: Array<[string, Breakdown | undefined]> = [
    ["کل فراخوان‌ها", breakdown.notice_total],
    ["فراخوان جدید امروز", breakdown.new_today],
    ["تحلیل‌نشده", breakdown.unanalyzed],
    ["پیشنهادی", breakdown.recommended],
    ["منتخب", breakdown.selected],
    ["ارسال‌شده", breakdown.submitted],
    ["در حال انقضا", breakdown.urgent],
    ["نتیجه موفق", breakdown.won],
  ];
  return <section dir="rtl" style={{margin:"0 0 14px",padding:"12px 14px",border:"1px solid #dbe3ec",borderRadius:14,background:"white",boxShadow:"0 4px 14px rgba(15,23,42,.035)"}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,flexWrap:"wrap",marginBottom:9}}>
      <div><b style={{fontSize:15}}>شاخص‌های واقعی فراخوان‌ها</b><small style={{display:"block",color:"#64748b",marginTop:2}}>محاسبه مستقیم از پایگاه‌داده؛ تفکیک مناقصه و استعلام</small></div>
      <small style={{color:"#64748b"}}>{metrics.analysis_basis === "active_run_remaining" ? "تحلیل‌نشده بر مبنای باقیمانده اجرای فعال تحلیل" : "تحلیل‌نشده بر مبنای وضعیت پردازش"}</small>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(175px,1fr))",gap:6}}>
      {cells.map(([label, value]) => <div key={label} style={{padding:"8px 9px",border:"1px solid #edf1f5",borderRadius:9,background:"#fbfdff"}}>
        <span style={{display:"block",fontSize:11,color:"#64748b"}}>{label}</span>
        <b style={{display:"block",fontSize:19,lineHeight:1.25,margin:"2px 0"}}>{fa.format(value?.total || 0)}</b>
        <small style={{fontSize:10.5,color:"#475569"}}>مناقصه {fa.format(value?.tender || 0)} · استعلام {fa.format(value?.inquiry || 0)}</small>
      </div>)}
      <div style={{padding:"8px 9px",border:"1px solid #edf1f5",borderRadius:9,background:"#fbfdff"}}>
        <span style={{display:"block",fontSize:11,color:"#64748b"}}>ارجاع مستقیم فعال</span>
        <b style={{display:"block",fontSize:19,lineHeight:1.25,margin:"2px 0"}}>{fa.format(metrics.direct?.active || 0)}</b>
        <small style={{fontSize:10.5,color:"#475569"}}>جدا از مناقصات و استعلامات</small>
      </div>
    </div>
  </section>;
}

export default function ProcurementCompactWorkflowEnhancement() {
  installCompactBrowseFetch();
  const initialFilters = typeof window === "undefined" ? { deadlineState:"" as DeadlineState, publishedOn:"" } : ((window as CompactWindow).__pdpCompactFilters || { deadlineState:"" as DeadlineState, publishedOn:"" });
  const [filters, setFilters] = useState<CompactFilters>(initialFilters);
  const [filterHost, setFilterHost] = useState<HTMLElement | null>(null);
  const [dashboardHost, setDashboardHost] = useState<HTMLElement | null>(null);
  const [context, setContext] = useState("");
  const [rows, setRows] = useState<RowPresentation[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  const applyFilters = useCallback((next: CompactFilters) => {
    setFilters(next);
    const guarded = window as CompactWindow;
    guarded.__pdpCompactFilters = next;
    guarded.__pdpPaginationPage = 1;
    emitProcurementUiSync({ source:"compact-workflow", bulkWorkspace:true });
  }, []);

  const loadMetrics = useCallback(() => {
    void fetch(METRICS_PATH, { credentials:"include", headers:{ Accept:"application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`metrics-${response.status}`);
        return await response.json() as DashboardMetrics;
      })
      .then(setMetrics)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    loadMetrics();
    const onSync = () => { setRevision((value) => value + 1); loadMetrics(); };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
  }, [loadMetrics]);

  useEffect(() => {
    let scheduled = false;
    const ensure = () => {
      scheduled = false;
      const main = document.querySelector<HTMLElement>("main[dir='rtl']");
      if (!main) return;
      const top = activeTopLabel();
      const workflow = activeWorkflowLabel();
      const nextContext = `${top}|${workflow}`;
      setContext((current) => current === nextContext ? current : nextContext);

      const liveBanner = Array.from(main.querySelectorAll<HTMLElement>("div")).find((div) =>
        normalize(div.querySelector(":scope > b")?.textContent) === "داده واقعی" && normalize(div.textContent).includes("PostgreSQL"),
      );
      if (liveBanner) liveBanner.style.display = "none";

      if (TOP_NOTICE_LABELS.has(top)) {
        const searchLabel = Array.from(main.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("جست‌وجو"));
        const filterBar = searchLabel?.parentElement;
        if (filterBar) {
          let host = document.getElementById(FILTER_HOST_ID);
          if (!host) {
            host = document.createElement("div");
            host.id = FILTER_HOST_ID;
            host.style.cssText = "display:contents";
            filterBar.appendChild(host);
          }
          if (host !== filterHost) setFilterHost(host);
        }
      } else if (filterHost) {
        setFilterHost(null);
      }

      const dashboardActive = top === "داشبورد مدیریتی";
      const newKpi = Array.from(main.querySelectorAll<HTMLElement>("article")).find((article) => normalize(article.querySelector("span")?.textContent) === "فراخوان جدید");
      const kpiContainer = newKpi?.parentElement as HTMLElement | null;
      if (dashboardActive && kpiContainer) {
        kpiContainer.style.display = "none";
        kpiContainer.dataset.pdpCompactHiddenKpis = "true";
        let host = document.getElementById(DASHBOARD_HOST_ID);
        if (!host) {
          host = document.createElement("div");
          host.id = DASHBOARD_HOST_ID;
          kpiContainer.parentElement?.insertBefore(host, kpiContainer);
        }
        if (host !== dashboardHost) setDashboardHost(host);
      } else {
        document.querySelectorAll<HTMLElement>("[data-pdp-compact-hidden-kpis='true']").forEach((node) => {
          node.style.display = "";
          delete node.dataset.pdpCompactHiddenKpis;
        });
        if (dashboardHost) setDashboardHost(null);
      }

      patchNoticeRows(new Map(rows.map((item) => [rowKey(item.title, item.employer_name), item])));
    };
    const observer = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(ensure);
    });
    observer.observe(document.body, { childList:true, subtree:true, attributes:true, attributeFilter:["class"] });
    ensure();
    return () => observer.disconnect();
  }, [filterHost, dashboardHost, rows]);

  useEffect(() => {
    const [top] = context.split("|");
    if (!TOP_NOTICE_LABELS.has(top)) {
      setRows([]);
      patchNoticeRows(new Map());
      return;
    }
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`${NOTICE_PATH}?ordering=-last_seen_at`, { credentials:"include", headers:{ Accept:"application/json" } });
        if (!response.ok) return;
        const payload = await response.json() as Collection<NoticeRow>;
        const items = Array.isArray(payload) ? payload : (payload.results || []);
        const guarded = window as CompactWindow;
        const nativeFetch = guarded.__pdpPaginationNativeFetch || window.fetch.bind(window);
        const expanded = await Promise.all(items.map(async (item): Promise<RowPresentation> => {
          let sources: SourceBadge[] = item.source_name ? [{ name:item.source_name, url:item.detail_url || item.source_url }] : [];
          if (Number(item.source_count || 0) > 1) {
            try {
              const detailResponse = await nativeFetch(`${NOTICE_PATH}${item.id}/`, { credentials:"include", headers:{ Accept:"application/json" } });
              if (detailResponse.ok) {
                const detail = await detailResponse.json() as NoticeDetail;
                const linked = (detail.source_links || []).map((link) => ({
                  name: normalize(link.source_notice?.source_name),
                  url: normalize(link.source_notice?.detail_url || link.source_notice?.source_url),
                })).filter((source) => source.name);
                if (linked.length) sources = linked;
              }
            } catch {
              // Keep the primary source if detail enrichment is temporarily unavailable.
            }
          }
          return { ...item, sources: orderedSources(sources) };
        }));
        if (active) setRows(expanded);
      } catch {
        if (active) setRows([]);
      }
    };
    void load();
    return () => { active = false; };
  }, [context, filters.deadlineState, filters.publishedOn, revision]);

  const rowMap = useMemo(() => new Map(rows.map((item) => [rowKey(item.title, item.employer_name), item])), [rows]);
  useEffect(() => { patchNoticeRows(rowMap); }, [rowMap, context]);

  const bulkDismiss = useCallback(async () => {
    const top = activeTopLabel();
    if (!TOP_NOTICE_LABELS.has(top) || activeWorkflowLabel() !== "پیشنهادی" || !rows.length || bulkBusy) return;
    const confirmed = window.confirm(`${fa.format(rows.length)} پیشنهاد همین صفحه از فهرست «پیشنهادی» حذف شود؟ خود مناقصه/استعلام و سابقه تحلیل حذف نمی‌شود.`);
    if (!confirmed) return;
    setBulkBusy(true);
    try {
      const token = await csrfToken();
      let failed = 0;
      for (const item of rows) {
        const response = await fetch(`${RECOMMENDED_PATH}${item.id}/dismiss/`, {
          method:"POST",
          credentials:"include",
          headers:{ "Content-Type":"application/json", "X-CSRFToken":token, Accept:"application/json" },
          body:JSON.stringify({ reason:"حذف گروهی از فهرست پیشنهادی همین صفحه توسط کاربر" }),
        });
        if (!response.ok) failed += 1;
      }
      if (failed) window.alert(`${fa.format(rows.length - failed)} مورد حذف شد و ${fa.format(failed)} مورد نیازمند تلاش مجدد است.`);
      emitProcurementUiSync({ source:"compact-workflow", bulkWorkspace:true, dashboard:true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "حذف گروهی پیشنهادها انجام نشد.");
    } finally {
      setBulkBusy(false);
    }
  }, [rows, bulkBusy]);

  const recommended = context.endsWith("|پیشنهادی") && TOP_NOTICE_LABELS.has(context.split("|")[0]);
  const inputStyle = { minHeight:34, border:"1px solid rgba(15,23,42,.16)", borderRadius:8, padding:"6px 8px", background:"white", font:"inherit", width:"100%" } as const;

  return <>
    {filterHost && createPortal(<>
      <label>وضعیت مهلت<select style={inputStyle} value={filters.deadlineState} onChange={(event) => applyFilters({ ...filters, deadlineState:event.target.value as DeadlineState })}>
        <option value="">همه وضعیت‌ها</option>
        <option value="expired">منقضی‌شده</option>
        <option value="expiring">در حال انقضا (تا ۳ روز)</option>
        <option value="available">فرصت دارد (بیش از ۳ روز)</option>
        <option value="unknown">مهلت نامشخص</option>
      </select></label>
      <label>تاریخ انتشار<div style={{display:"flex",gap:4}}><input type="date" style={inputStyle} value={filters.publishedOn} onChange={(event) => applyFilters({ ...filters, publishedOn:event.target.value })}/><button type="button" onClick={() => applyFilters({ ...filters, publishedOn:yesterdayIso() })} style={{minHeight:34,border:"1px solid #cbd5e1",borderRadius:8,background:"white",font:"inherit",fontSize:11,padding:"4px 7px",whiteSpace:"nowrap"}}>دیروز</button></div></label>
      {recommended && <div style={{display:"flex",alignItems:"end"}}><button type="button" disabled={bulkBusy || !rows.length} onClick={() => void bulkDismiss()} style={{minHeight:34,border:"1px solid #fecaca",borderRadius:8,background:"#fff1f2",color:"#be123c",font:"inherit",fontSize:11,fontWeight:700,padding:"6px 9px",cursor:"pointer",opacity:bulkBusy || !rows.length ? .55 : 1}}>{bulkBusy ? "در حال حذف..." : `حذف پیشنهادهای این صفحه (${fa.format(rows.length)})`}</button></div>}
      {(filters.deadlineState || filters.publishedOn) && <div style={{display:"flex",alignItems:"end"}}><button type="button" onClick={() => applyFilters({ deadlineState:"", publishedOn:"" })} style={{minHeight:34,border:"1px solid #cbd5e1",borderRadius:8,background:"#f8fafc",font:"inherit",fontSize:11,padding:"6px 8px"}}>پاک‌کردن مهلت/تاریخ</button></div>}
    </>, filterHost)}
    {dashboardHost && metrics && createPortal(<DashboardSummary metrics={metrics}/>, dashboardHost)}
  </>;
}
