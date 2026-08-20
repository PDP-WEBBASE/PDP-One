"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync } from "./procurementUiSync";

type PageSize = 30 | 50 | 100;
type PaginationMeta = {
  count: number;
  page: number;
  pageSize: PageSize;
  contextKey: string;
  top?: string;
  workflow?: string;
};
type PaginatedPayload<T = unknown> = {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: T[];
  [key: string]: unknown;
};
type PaginationWindow = Window & {
  __pdpPaginationInstalled?: boolean;
  __pdpPaginationNativeFetch?: typeof window.fetch;
  __pdpPaginationPage?: number;
  __pdpPaginationPageSize?: PageSize;
  __pdpPaginationContextKey?: string;
};

const META_EVENT = "pdp-procurement-pagination-meta";
const HOST_ID = "pdp-procurement-pagination-host";
const API_PREFIX = "/api/v1/procurement/";
const NOTICE_PATH = `${API_PREFIX}notices/`;
const RECOMMENDED_PATH = `${API_PREFIX}recommended-notices/`;
const DIRECT_PATH = `${API_PREFIX}direct-opportunities/`;
const TOP_LABELS = new Set(["داشبورد مدیریتی", "مناقصات", "استعلامات", "ارجاعات مستقیم", "مدیریت زیرسامانه"]);
const WORKFLOW_LABELS = new Set([
  "کل مناقصات", "مناقصات ۳ روز اخیر", "کل استعلامات", "استعلامات ۳ روز اخیر", "کل ارجاعات مستقیم",
  "پیشنهادی", "منتخب", "ارسال‌شده", "نتایج",
]);
const fa = new Intl.NumberFormat("fa-IR");

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function parsedUrl(value: string) {
  try {
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
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
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("button"));
  const selected = buttons.find((button) => {
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

function fieldValue(labelPrefix: string) {
  const section = findListSection();
  const root: ParentNode = section || document;
  const label = Array.from(root.querySelectorAll<HTMLLabelElement>("label")).find((candidate) =>
    normalize(candidate.textContent).startsWith(labelPrefix),
  );
  const field = label?.querySelector<HTMLInputElement | HTMLSelectElement>("input,select");
  return normalize(field?.value);
}

function currentFilters() {
  return {
    search: fieldValue("جست‌وجو"),
    source: fieldValue("منبع"),
    province: fieldValue("استان"),
    importance: fieldValue("اهمیت"),
    urgency: fieldValue("فوریت"),
    directType: fieldValue("نوع ارجاع"),
  };
}

function buildContextKey(top: string, workflow: string, filters: ReturnType<typeof currentFilters>) {
  return JSON.stringify([top, workflow, filters.search, filters.source, filters.province, filters.importance, filters.urgency, filters.directType]);
}

function addCommonFilters(url: URL, filters: ReturnType<typeof currentFilters>) {
  if (filters.search) url.searchParams.set("search", filters.search);
  else url.searchParams.delete("search");
  if (filters.province) url.searchParams.set("province", filters.province);
  else url.searchParams.delete("province");
  if (filters.importance) url.searchParams.set("importance", filters.importance);
  else url.searchParams.delete("importance");
  if (filters.urgency) url.searchParams.set("urgency", filters.urgency);
  else url.searchParams.delete("urgency");
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

function emptyCollectionResponse() {
  return new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function currentPageState() {
  const guarded = window as PaginationWindow;
  return {
    page: Math.max(1, guarded.__pdpPaginationPage || 1),
    pageSize: guarded.__pdpPaginationPageSize || 50,
  };
}

function setPage(page: number) {
  (window as PaginationWindow).__pdpPaginationPage = Math.max(1, page);
}

function setPageSize(pageSize: PageSize) {
  const guarded = window as PaginationWindow;
  guarded.__pdpPaginationPageSize = pageSize;
  guarded.__pdpPaginationPage = 1;
}

function emitRefresh() {
  emitProcurementUiSync({ source: "pagination", bulkWorkspace: true });
}

function configureNoticeRequest(url: URL, top: string, workflow: string, filters: ReturnType<typeof currentFilters>) {
  url.pathname = workflow === "پیشنهادی" ? RECOMMENDED_PATH : NOTICE_PATH;
  url.search = "";
  url.searchParams.set("resolved_notice_type", top === "مناقصات" ? "tender" : "inquiry");
  url.searchParams.set("ordering", "-publication_sort,-last_seen_at,-id");

  if (workflow === "مناقصات ۳ روز اخیر" || workflow === "استعلامات ۳ روز اخیر") {
    url.searchParams.set("recent_days", "3");
  } else if (workflow === "پیشنهادی") {
    url.searchParams.set("actionable", "true");
  } else if (workflow === "منتخب") {
    url.searchParams.set("workflow_view", "selected");
  } else if (workflow === "ارسال‌شده") {
    url.searchParams.set("workflow_view", "submitted");
  } else if (workflow === "نتایج") {
    url.searchParams.set("workflow_view", "results");
  }

  addCommonFilters(url, filters);
  if (filters.source) url.searchParams.set("source_name", filters.source);
}

function configureDirectRequest(url: URL, workflow: string, filters: ReturnType<typeof currentFilters>) {
  url.pathname = DIRECT_PATH;
  url.search = "";
  url.searchParams.set("ordering", "-last_activity_at,-id");
  if (workflow === "پیشنهادی") url.searchParams.set("workflow_view", "recommended");
  else if (workflow === "منتخب") url.searchParams.set("workflow_view", "selected");
  else if (workflow === "ارسال‌شده") url.searchParams.set("workflow_view", "submitted");
  else if (workflow === "نتایج") url.searchParams.set("workflow_view", "results");
  addCommonFilters(url, filters);
  if (filters.directType) url.searchParams.set("opportunity_type", filters.directType);
}

function configureDashboardRequest(url: URL, isDirect: boolean) {
  url.search = "";
  if (isDirect) {
    url.pathname = DIRECT_PATH;
    url.searchParams.set("workflow_view", "active");
    url.searchParams.set("ordering", "-last_activity_at,-id");
  } else {
    url.pathname = NOTICE_PATH;
    url.searchParams.set("workflow_view", "active");
    url.searchParams.set("ordering", "-publication_sort,-last_seen_at,-id");
  }
}

function installPaginationFetchGuard() {
  if (typeof window === "undefined") return;
  const guarded = window as PaginationWindow;
  if (guarded.__pdpPaginationInstalled) return;
  const nativeFetch = window.fetch.bind(window);
  guarded.__pdpPaginationNativeFetch = nativeFetch;
  guarded.__pdpPaginationInstalled = true;
  guarded.__pdpPaginationPage = 1;
  guarded.__pdpPaginationPageSize = 50;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return nativeFetch(input, init);
    const original = parsedUrl(requestUrl(input));
    if (!original || original.origin !== window.location.origin) return nativeFetch(input, init);
    const isNoticeCollection = original.pathname === NOTICE_PATH || original.pathname === RECOMMENDED_PATH;
    const isDirectCollection = original.pathname === DIRECT_PATH;
    if (!isNoticeCollection && !isDirectCollection) return nativeFetch(input, init);

    const top = activeTopTab();
    const workflow = activeWorkflow();
    const filters = currentFilters();
    const contextKey = buildContextKey(top, workflow, filters);
    const activeNoticeTab = top === "مناقصات" || top === "استعلامات";
    const activeDirectTab = top === "ارجاعات مستقیم";
    const dashboard = top === "داشبورد مدیریتی" || !top;

    if (!dashboard && isNoticeCollection && !activeNoticeTab) return emptyCollectionResponse();
    if (!dashboard && isDirectCollection && !activeDirectTab) return emptyCollectionResponse();

    if (!dashboard && guarded.__pdpPaginationContextKey !== contextKey) {
      guarded.__pdpPaginationContextKey = contextKey;
      guarded.__pdpPaginationPage = 1;
    }
    const state = currentPageState();
    const nextUrl = new URL(original.toString());

    if (dashboard) {
      configureDashboardRequest(nextUrl, isDirectCollection);
      nextUrl.searchParams.set("page", "1");
      nextUrl.searchParams.set("page_size", "50");
    } else if (activeNoticeTab && isNoticeCollection) {
      configureNoticeRequest(nextUrl, top, workflow, filters);
      nextUrl.searchParams.set("page", String(state.page));
      nextUrl.searchParams.set("page_size", String(state.pageSize));
    } else if (activeDirectTab && isDirectCollection) {
      configureDirectRequest(nextUrl, workflow, filters);
      nextUrl.searchParams.set("page", String(state.page));
      nextUrl.searchParams.set("page_size", String(state.pageSize));
    }

    const response = await nativeFetch(`${nextUrl.pathname}${nextUrl.search}`, init);
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
    try {
      const payload = await response.clone().json() as PaginatedPayload;
      if (!Array.isArray(payload) && Array.isArray(payload.results)) {
        if (!dashboard) {
          window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: {
            count: Number(payload.count || 0),
            page: state.page,
            pageSize: state.pageSize,
            contextKey,
            top,
            workflow,
          } }));
        }
        return jsonResponse(response, { ...payload, next: null, previous: null });
      }
    } catch {
      return response;
    }
    return response;
  };
}

function findListSection() {
  const top = activeTopTab();
  if (!new Set(["مناقصات", "استعلامات", "ارجاعات مستقیم"]).has(top)) return null;
  const workflow = activeWorkflow();
  if (!workflow) return null;
  const workflowButton = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
    normalize(button.textContent) === workflow && Boolean(normalize(button.getAttribute("class"))),
  );
  return workflowButton?.closest("section") || null;
}

function ensureHost() {
  const section = findListSection();
  if (!section) return null;
  let host = document.getElementById(HOST_ID);
  if (!host) {
    host = document.createElement("div");
    host.id = HOST_ID;
  }
  if (host.parentElement !== section) section.appendChild(host);
  return host;
}

function pageTokens(current: number, total: number) {
  const keep = new Set([1, total, current - 2, current - 1, current, current + 1, current + 2]);
  const values = Array.from(keep).filter((value) => value >= 1 && value <= total).sort((a, b) => a - b);
  const tokens: Array<number | "…"> = [];
  values.forEach((value, index) => {
    const previous = values[index - 1];
    if (previous && value - previous > 1) tokens.push("…");
    tokens.push(value);
  });
  return tokens;
}

function PaginationBar({ meta }: { meta: PaginationMeta }) {
  const totalPages = Math.max(1, Math.ceil(meta.count / meta.pageSize));
  const current = Math.min(meta.page, totalPages);
  const tokens = useMemo(() => pageTokens(current, totalPages), [current, totalPages]);
  const buttonStyle = {
    minWidth: 34, minHeight: 32, border: "1px solid #cbd5e1", borderRadius: 8,
    background: "white", color: "#334155", font: "inherit", cursor: "pointer",
  } as const;
  const activeStyle = { ...buttonStyle, background: "#155e75", color: "white", borderColor: "#155e75", fontWeight: 700 } as const;

  return <div dir="rtl" style={{marginTop:12,padding:"10px 12px",border:"1px solid #dbe3ec",borderRadius:12,background:"#f8fafc",display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,flexWrap:"wrap"}}>
    <div style={{display:"flex",alignItems:"center",gap:7,flexWrap:"wrap"}}>
      <button type="button" disabled={current <= 1} style={{...buttonStyle,opacity:current <= 1 ? 0.45 : 1}} onClick={() => { setPage(current - 1); emitRefresh(); }}>قبلی</button>
      {tokens.map((token, index) => token === "…" ? <span key={`ellipsis-${index}`} style={{padding:"0 2px"}}>…</span> : <button key={token} type="button" style={token === current ? activeStyle : buttonStyle} onClick={() => { setPage(token); emitRefresh(); }}>{fa.format(token)}</button>)}
      <button type="button" disabled={current >= totalPages} style={{...buttonStyle,opacity:current >= totalPages ? 0.45 : 1}} onClick={() => { setPage(current + 1); emitRefresh(); }}>بعدی</button>
    </div>
    <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",fontSize:12,color:"#475569"}}>
      <b>صفحه {fa.format(current)} از {fa.format(totalPages)} — مجموع {fa.format(meta.count)} رکورد</b>
      <label style={{display:"flex",alignItems:"center",gap:6}}>نمایش در صفحه
        <select value={meta.pageSize} onChange={(event) => { setPageSize(Number(event.target.value) as PageSize); emitRefresh(); }} style={{minHeight:32,border:"1px solid #cbd5e1",borderRadius:8,background:"white",padding:"4px 8px",font:"inherit"}}>
          <option value={30}>۳۰</option>
          <option value={50}>۵۰</option>
          <option value={100}>۱۰۰</option>
        </select>
      </label>
    </div>
  </div>;
}

export default function ProcurementPaginationStableEnhancement() {
  installPaginationFetchGuard();
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [meta, setMeta] = useState<PaginationMeta | null>(null);

  useEffect(() => {
    let searchTimer = 0;
    let syncTimer = 0;
    let hostFrame = 0;
    let transitionFrame = 0;

    const refreshHost = () => {
      if (hostFrame) return;
      hostFrame = window.requestAnimationFrame(() => {
        hostFrame = 0;
        const nextHost = ensureHost();
        setHost((current) => current === nextHost ? current : nextHost);
      });
    };

    const runRefresh = () => {
      setPage(1);
      emitRefresh();
      refreshHost();
    };

    const refreshAfterCommit = (expectedLabel = "", topLevel = false, attempt = 0) => {
      window.cancelAnimationFrame(transitionFrame);
      transitionFrame = window.requestAnimationFrame(() => {
        const active = topLevel ? activeTopTab() : activeWorkflow();
        if (expectedLabel && active !== expectedLabel && attempt < 3) {
          refreshAfterCommit(expectedLabel, topLevel, attempt + 1);
          return;
        }
        runRefresh();
      });
    };

    const resetAndRefresh = (delay = 0) => {
      window.clearTimeout(syncTimer);
      syncTimer = window.setTimeout(() => refreshAfterCommit(), delay);
    };

    const onMeta = (event: Event) => {
      const detail = (event as CustomEvent<PaginationMeta>).detail;
      if (!detail) return;
      const top = activeTopTab();
      const workflow = activeWorkflow();
      if (detail.top && detail.top !== top) return;
      if (detail.workflow && detail.workflow !== workflow) return;
      setMeta(detail);
      refreshHost();
    };

    const onClick = (event: MouseEvent) => {
      const button = (event.target as HTMLElement | null)?.closest("button");
      const label = normalize(button?.textContent);
      if (TOP_LABELS.has(label)) {
        setMeta(null);
        refreshAfterCommit(label, true);
        return;
      }
      if (WORKFLOW_LABELS.has(label)) {
        setMeta(null);
        refreshAfterCommit(label, false);
        return;
      }
      if (label === "پاک‌کردن") {
        setMeta(null);
        refreshAfterCommit();
      }
    };

    const onInput = (event: Event) => {
      const target = event.target as HTMLInputElement | null;
      if (!target || target.tagName !== "INPUT") return;
      const label = target.closest("label");
      if (!label || !normalize(label.textContent).startsWith("جست‌وجو")) return;
      setMeta(null);
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => resetAndRefresh(0), 350);
    };

    const onChange = (event: Event) => {
      const target = event.target as HTMLSelectElement | null;
      if (!target || target.tagName !== "SELECT" || target.closest(`#${HOST_ID}`)) return;
      const label = target.closest("label");
      const text = normalize(label?.textContent);
      if (["منبع", "استان", "اهمیت", "فوریت", "نوع ارجاع"].some((prefix) => text.startsWith(prefix))) {
        setMeta(null);
        refreshAfterCommit();
      }
    };

    const observer = new MutationObserver(refreshHost);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener(META_EVENT, onMeta);
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("change", onChange);
    refreshHost();

    return () => {
      observer.disconnect();
      window.removeEventListener(META_EVENT, onMeta);
      document.removeEventListener("click", onClick);
      document.removeEventListener("input", onInput);
      document.removeEventListener("change", onChange);
      window.clearTimeout(searchTimer);
      window.clearTimeout(syncTimer);
      window.cancelAnimationFrame(hostFrame);
      window.cancelAnimationFrame(transitionFrame);
    };
  }, []);

  return host && meta ? createPortal(<PaginationBar meta={meta} />, host) : null;
}
