"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync } from "./procurementUiSync";
import {
  getProcurementStableViewState,
  installProcurementStableViewState,
  PROCUREMENT_STABLE_VIEW_STATE_EVENT,
  stableWorkflowLabel,
  type ProcurementStableViewState,
} from "./procurementStableViewState";

type PageSize = 30 | 50 | 100;
type PaginationMeta = {
  count: number;
  page: number;
  pageSize: PageSize;
  contextKey: string;
  top: ProcurementStableViewState["top"];
  workflow: ProcurementStableViewState["workflow"];
};
type PaginatedPayload<T = Record<string, unknown>> = {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: T[];
  page?: number;
  page_size?: number;
  [key: string]: unknown;
};
type CachedPage = { payload: PaginatedPayload; storedAt: number; meta?: PaginationMeta };
type PaginationWindow = Window & {
  __pdpPaginationInstalled?: boolean;
  __pdpPaginationNativeFetch?: typeof window.fetch;
  __pdpPaginationPage?: number;
  __pdpPaginationPageSize?: PageSize;
  __pdpStableListCache?: Map<string, CachedPage>;
  __pdpCompactDeadlineStatus?: string;
  __pdpCompactPublishedOn?: string;
};

const API_PREFIX = "/api/v1/procurement/";
const NOTICE_PATH = `${API_PREFIX}notices/`;
const RECOMMENDED_PATH = `${API_PREFIX}recommended-notices/`;
const DIRECT_PATH = `${API_PREFIX}direct-opportunities/`;
const COMPACT_NOTICE_PATH = `${API_PREFIX}ui/notices/`;
const META_EVENT = "pdp-procurement-pagination-meta";
const DATA_EVENT = "pdp-procurement-compact-notice-data";
const DIRECT_DATA_EVENT = "pdp-procurement-direct-page-data";
const HOST_ID = "pdp-procurement-pagination-host";
const CACHE_TTL_MS = 5 * 60 * 1000;
const MAX_CACHE_ENTRIES = 60;
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

function fieldValue(labelPrefix: string) {
  const label = Array.from(document.querySelectorAll<HTMLLabelElement>("label")).find((candidate) =>
    normalize(candidate.textContent).startsWith(labelPrefix),
  );
  const field = label?.querySelector<HTMLInputElement | HTMLSelectElement>("input,select");
  return normalize(field?.value);
}

function currentFilters() {
  const guarded = window as PaginationWindow;
  return {
    search: fieldValue("جست‌وجو"),
    source: fieldValue("منبع"),
    province: fieldValue("استان"),
    importance: fieldValue("اهمیت"),
    urgency: fieldValue("فوریت"),
    directType: fieldValue("نوع ارجاع"),
    deadlineStatus: guarded.__pdpCompactDeadlineStatus || "",
    publishedOn: guarded.__pdpCompactPublishedOn || "",
  };
}

function listCache() {
  const guarded = window as PaginationWindow;
  if (!guarded.__pdpStableListCache) guarded.__pdpStableListCache = new Map();
  return guarded.__pdpStableListCache;
}

function remember(key: string, value: CachedPage) {
  const cache = listCache();
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value as string | undefined;
    if (!oldest) break;
    cache.delete(oldest);
  }
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

function stateStillMatches(expected: ProcurementStableViewState) {
  const current = getProcurementStableViewState();
  return current.top === expected.top && current.workflow === expected.workflow;
}

function workflowCode(workflow: ProcurementStableViewState["workflow"]) {
  if (workflow === "recommended") return "recommended";
  if (workflow === "selected") return "selected";
  if (workflow === "submitted") return "submitted";
  if (workflow === "results") return "results";
  return "recent";
}

function addFilters(params: URLSearchParams, filters: ReturnType<typeof currentFilters>) {
  if (filters.search) params.set("search", filters.search);
  if (filters.source) params.set("source_name", filters.source);
  if (filters.province) params.set("province", filters.province);
  if (filters.importance) params.set("importance", filters.importance);
  if (filters.urgency) params.set("urgency", filters.urgency);
  if (filters.deadlineStatus) params.set("deadline_status", filters.deadlineStatus);
  if (filters.publishedOn) params.set("published_on", filters.publishedOn);
}

function normalizeCompactPayload(payload: PaginatedPayload, state: ProcurementStableViewState) {
  const workflow = workflowCode(state.workflow);
  const results = Array.isArray(payload.results) ? payload.results.map((item) => {
    const normalizedItem = { ...item } as Record<string, unknown>;
    const publishedDate = String(normalizedItem.published_date || "").trim();
    if (workflow === "recent" && publishedDate) normalizedItem.first_seen_at = `${publishedDate}T12:00:00+03:30`;
    if (workflow === "recommended") normalizedItem.is_recommended = true;
    return normalizedItem;
  }) : [];
  return { ...payload, next: null, previous: null, results };
}

function dispatchNoticeEvents(payload: PaginatedPayload, meta: PaginationMeta) {
  window.dispatchEvent(new CustomEvent(DATA_EVENT, { detail: payload }));
  window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: meta }));
}

async function boundedJsonFetch(nativeFetch: typeof window.fetch, url: string, init: RequestInit | undefined, cacheKey: string | null, meta: PaginationMeta | undefined, state: ProcurementStableViewState, dispatchData = false) {
  if (cacheKey) {
    const cached = listCache().get(cacheKey);
    if (cached && Date.now() - cached.storedAt <= CACHE_TTL_MS) {
      if (cached.meta && stateStillMatches(state)) {
        if (dispatchData) window.dispatchEvent(new CustomEvent(DATA_EVENT, { detail: cached.payload }));
        window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: cached.meta }));
      }
      return new Response(JSON.stringify(cached.payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (cached) listCache().delete(cacheKey);
  }
  const response = await nativeFetch(url, init);
  if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
  try {
    const raw = await response.clone().json() as PaginatedPayload;
    const payload = { ...raw, next: null, previous: null };
    if (cacheKey) remember(cacheKey, { payload, storedAt: Date.now(), meta });
    if (meta && stateStillMatches(state)) {
      if (dispatchData) dispatchNoticeEvents(payload, meta);
      else window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: meta }));
    }
    return jsonResponse(response, payload);
  } catch {
    return response;
  }
}

function installPaginationFetchGuard() {
  if (typeof window === "undefined") return;
  installProcurementStableViewState();
  const guarded = window as PaginationWindow;
  if (guarded.__pdpPaginationInstalled) return;
  guarded.__pdpPaginationInstalled = true;
  guarded.__pdpPaginationPage = guarded.__pdpPaginationPage || 1;
  guarded.__pdpPaginationPageSize = guarded.__pdpPaginationPageSize || 50;
  const nativeFetch = window.fetch.bind(window);
  guarded.__pdpPaginationNativeFetch = nativeFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = requestMethod(input, init);
    const original = parsedUrl(requestUrl(input));
    if (!original || original.origin !== window.location.origin) return nativeFetch(input, init);
    if (method !== "GET") {
      if (original.pathname.startsWith(API_PREFIX)) listCache().clear();
      return nativeFetch(input, init);
    }
    const isNotice = original.pathname === NOTICE_PATH || original.pathname === RECOMMENDED_PATH;
    const isDirect = original.pathname === DIRECT_PATH;
    if (!isNotice && !isDirect) return nativeFetch(input, init);
    const state = getProcurementStableViewState();
    const pageState = currentPageState();
    const filters = currentFilters();

    if (state.top === "tenders" || state.top === "inquiries") {
      if (isDirect) return emptyCollectionResponse();
      const params = new URLSearchParams();
      params.set("notice_type", state.top === "tenders" ? "tender" : "inquiry");
      params.set("workflow", workflowCode(state.workflow));
      params.set("page", String(pageState.page));
      params.set("page_size", String(pageState.pageSize));
      addFilters(params, filters);
      const contextKey = JSON.stringify([state.top, state.workflow, ...Array.from(params.entries())]);
      const meta: PaginationMeta = { count: 0, page: pageState.page, pageSize: pageState.pageSize, contextKey, top: state.top, workflow: state.workflow };
      const cacheKey = `notice:${contextKey}`;
      const response = await boundedJsonFetch(nativeFetch, `${COMPACT_NOTICE_PATH}?${params.toString()}`, init, cacheKey, meta, state, false);
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
      try {
        const raw = await response.clone().json() as PaginatedPayload;
        const normalized = normalizeCompactPayload(raw, state);
        const correctedMeta = { ...meta, count: Number(normalized.count || 0) };
        remember(cacheKey, { payload: normalized, storedAt: Date.now(), meta: correctedMeta });
        if (stateStillMatches(state)) dispatchNoticeEvents(normalized, correctedMeta);
        return jsonResponse(response, normalized);
      } catch {
        return response;
      }
    }

    if (state.top === "direct") {
      if (isNotice) return emptyCollectionResponse();
      const nextUrl = new URL(original.toString());
      nextUrl.search = "";
      nextUrl.searchParams.set("ordering", "-last_activity_at,-id");
      if (state.workflow === "recommended") nextUrl.searchParams.set("workflow_view", "recommended");
      else if (state.workflow === "selected") nextUrl.searchParams.set("workflow_view", "selected");
      else if (state.workflow === "submitted") nextUrl.searchParams.set("workflow_view", "submitted");
      else if (state.workflow === "results") nextUrl.searchParams.set("workflow_view", "results");
      if (filters.search) nextUrl.searchParams.set("search", filters.search);
      if (filters.province) nextUrl.searchParams.set("province", filters.province);
      if (filters.importance) nextUrl.searchParams.set("importance", filters.importance);
      if (filters.urgency) nextUrl.searchParams.set("urgency", filters.urgency);
      if (filters.directType) nextUrl.searchParams.set("opportunity_type", filters.directType);
      nextUrl.searchParams.set("page", String(pageState.page));
      nextUrl.searchParams.set("page_size", String(pageState.pageSize));
      const contextKey = JSON.stringify([state.top, state.workflow, nextUrl.search]);
      const meta: PaginationMeta = { count: 0, page: pageState.page, pageSize: pageState.pageSize, contextKey, top: state.top, workflow: state.workflow };
      const cacheKey = `direct:${contextKey}`;
      const response = await boundedJsonFetch(nativeFetch, `${nextUrl.pathname}${nextUrl.search}`, init, cacheKey, meta, state);
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
      try {
        const payload = await response.clone().json() as PaginatedPayload;
        const correctedMeta = { ...meta, count: Number(payload.count || 0) };
        remember(cacheKey, { payload, storedAt: Date.now(), meta: correctedMeta });
        if (stateStillMatches(state)) {
          window.dispatchEvent(new CustomEvent(DIRECT_DATA_EVENT, { detail: payload }));
          window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: correctedMeta }));
        }
      } catch {
        // Preserve the real response.
      }
      return response;
    }

    const nextUrl = new URL(original.toString());
    nextUrl.searchParams.set("page", "1");
    nextUrl.searchParams.set("page_size", "50");
    if (isNotice) {
      nextUrl.searchParams.set("workflow_view", "active");
      nextUrl.searchParams.set("ordering", "-publication_sort,-last_seen_at,-id");
    } else {
      nextUrl.searchParams.set("workflow_view", "active");
      nextUrl.searchParams.set("ordering", "-last_activity_at,-id");
    }
    return boundedJsonFetch(nativeFetch, `${nextUrl.pathname}${nextUrl.search}`, init, null, undefined, state);
  };
}

function findListSection() {
  const state = getProcurementStableViewState();
  if (state.top !== "tenders" && state.top !== "inquiries" && state.top !== "direct") return null;
  const expectedLabel = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((candidate) => !candidate.closest("nav") && normalize(candidate.textContent) === expectedLabel);
  return button?.closest("section") || null;
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
  const buttonStyle = { minWidth:34,minHeight:32,border:"1px solid #cbd5e1",borderRadius:8,background:"white",color:"#334155",font:"inherit",cursor:"pointer" } as const;
  const activeStyle = { ...buttonStyle,background:"#155e75",color:"white",borderColor:"#155e75",fontWeight:700 } as const;
  return <div dir="rtl" style={{marginTop:12,padding:"10px 12px",border:"1px solid #dbe3ec",borderRadius:12,background:"#f8fafc",display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,flexWrap:"wrap"}}><div style={{display:"flex",alignItems:"center",gap:7,flexWrap:"wrap"}}><button type="button" disabled={current <= 1} style={{...buttonStyle,opacity:current <= 1 ? .45 : 1}} onClick={() => { setPage(current - 1); emitRefresh(); }}>قبلی</button>{tokens.map((token,index) => token === "…" ? <span key={`ellipsis-${index}`}>…</span> : <button key={token} type="button" style={token === current ? activeStyle : buttonStyle} onClick={() => { setPage(token); emitRefresh(); }}>{fa.format(token)}</button>)}<button type="button" disabled={current >= totalPages} style={{...buttonStyle,opacity:current >= totalPages ? .45 : 1}} onClick={() => { setPage(current + 1); emitRefresh(); }}>بعدی</button></div><div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",fontSize:12,color:"#475569"}}><b>صفحه {fa.format(current)} از {fa.format(totalPages)}</b><span>مجموع {fa.format(meta.count)} رکورد</span><label style={{display:"flex",alignItems:"center",gap:5}}>نمایش در صفحه<select value={meta.pageSize} onChange={(event) => { setPageSize(Number(event.target.value) as PageSize); emitRefresh(); }}><option value={30}>۳۰</option><option value={50}>۵۰</option><option value={100}>۱۰۰</option></select></label></div></div>;
}

export default function ProcurementPaginationStableEnhancement() {
  installPaginationFetchGuard();
  const [meta, setMeta] = useState<PaginationMeta | null>(null);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let filterTimer = 0;
    let frame = 0;
    const scheduleHost = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => setHost(ensureHost()));
    };
    const refreshForState = () => {
      setMeta(null);
      setPage(1);
      scheduleHost();
      window.requestAnimationFrame(emitRefresh);
    };
    const onState = () => refreshForState();
    const onMeta = (event: Event) => {
      const detail = (event as CustomEvent<PaginationMeta>).detail;
      if (!detail) return;
      const state = getProcurementStableViewState();
      if (detail.top !== state.top || detail.workflow !== state.workflow) return;
      setMeta(detail);
      scheduleHost();
    };
    const onFieldChange = (event: Event) => {
      const field = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement ? event.target : null;
      const label = field?.closest("label");
      if (!field || !label || !findListSection()?.contains(field)) return;
      const text = normalize(label.textContent);
      if (!["جست‌وجو","منبع","استان","اهمیت","فوریت","نوع ارجاع"].some((prefix) => text.startsWith(prefix))) return;
      window.clearTimeout(filterTimer);
      filterTimer = window.setTimeout(() => { setPage(1); setMeta(null); emitRefresh(); }, field instanceof HTMLInputElement ? 250 : 0);
    };
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    window.addEventListener(META_EVENT, onMeta);
    document.addEventListener("input", onFieldChange, true);
    document.addEventListener("change", onFieldChange, true);
    scheduleHost();
    return () => {
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
      window.removeEventListener(META_EVENT, onMeta);
      document.removeEventListener("input", onFieldChange, true);
      document.removeEventListener("change", onFieldChange, true);
      window.clearTimeout(filterTimer);
      window.cancelAnimationFrame(frame);
    };
  }, []);
  return host && meta ? createPortal(<PaginationBar meta={meta} />, host) : null;
}
