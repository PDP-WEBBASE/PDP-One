"use client";

import { useEffect } from "react";
import { PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type PageSize = 30 | 50 | 100;
type CacheKind = "notice" | "direct";
type PaginationMeta = {
  count: number;
  page: number;
  pageSize: PageSize;
  contextKey: string;
};
type PaginatedPayload = {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: unknown[];
  [key: string]: unknown;
};
type CachedPage = {
  payload: PaginatedPayload;
  meta: PaginationMeta;
  storedAt: number;
};
type CacheWindow = Window & {
  __pdpTabCacheInstalled?: boolean;
  __pdpTabCachePreviousFetch?: typeof window.fetch;
  __pdpTabPageCache?: Map<string, CachedPage>;
  __pdpPaginationPage?: number;
  __pdpPaginationPageSize?: PageSize;
};

const API_PREFIX = "/api/v1/procurement/";
const NOTICE_PATH = `${API_PREFIX}notices/`;
const RECOMMENDED_PATH = `${API_PREFIX}recommended-notices/`;
const DIRECT_PATH = `${API_PREFIX}direct-opportunities/`;
const META_EVENT = "pdp-procurement-pagination-meta";
const TOP_LABELS = new Set(["داشبورد مدیریتی", "مناقصات", "استعلامات", "ارجاعات مستقیم", "مدیریت زیرسامانه"]);
const WORKFLOW_LABELS = new Set([
  "کل مناقصات", "مناقصات ۳ روز اخیر", "کل استعلامات", "استعلامات ۳ روز اخیر", "کل ارجاعات مستقیم",
  "پیشنهادی", "منتخب", "ارسال‌شده", "نتایج",
]);
const MAX_CACHE_ENTRIES = 60;
const CACHE_TTL_MS = 5 * 60 * 1000;

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function parsedUrl(value: string) {
  try {
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
}

function activeButtonLabel(labels: Set<string>) {
  return normalize(Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((button) => {
    const label = normalize(button.textContent);
    return labels.has(label) && Boolean(normalize(button.className));
  })?.textContent);
}

function fieldValue(labelPrefix: string) {
  const label = Array.from(document.querySelectorAll<HTMLLabelElement>("label")).find((candidate) =>
    normalize(candidate.textContent).startsWith(labelPrefix),
  );
  const field = label?.querySelector<HTMLInputElement | HTMLSelectElement>("input,select");
  return normalize(field?.value);
}

function currentPageState() {
  const guarded = window as CacheWindow;
  return {
    page: Math.max(1, guarded.__pdpPaginationPage || 1),
    pageSize: guarded.__pdpPaginationPageSize || 50,
  };
}

function pageCache() {
  const guarded = window as CacheWindow;
  if (!guarded.__pdpTabPageCache) guarded.__pdpTabPageCache = new Map();
  return guarded.__pdpTabPageCache;
}

function clearKind(kind: CacheKind) {
  const prefix = `${kind}:`;
  const cache = pageCache();
  for (const key of Array.from(cache.keys())) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}

function remember(key: string, value: CachedPage) {
  const cache = pageCache();
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value as string | undefined;
    if (!oldest) break;
    cache.delete(oldest);
  }
}

function currentCacheContext(kind: CacheKind) {
  const top = activeButtonLabel(TOP_LABELS);
  const workflow = activeButtonLabel(WORKFLOW_LABELS);
  const noticeActive = top === "مناقصات" || top === "استعلامات";
  const directActive = top === "ارجاعات مستقیم";
  if ((kind === "notice" && !noticeActive) || (kind === "direct" && !directActive)) return null;

  const state = currentPageState();
  const filters = [
    fieldValue("جست‌وجو"),
    fieldValue("منبع"),
    fieldValue("استان"),
    fieldValue("اهمیت"),
    fieldValue("فوریت"),
    fieldValue("نوع ارجاع"),
  ];
  const contextKey = JSON.stringify([top, workflow, ...filters]);
  return {
    key: `${kind}:${JSON.stringify([top, workflow, ...filters, state.page, state.pageSize])}`,
    metaBase: { page: state.page, pageSize: state.pageSize, contextKey },
  };
}

function dispatchMeta(meta: PaginationMeta) {
  window.dispatchEvent(new CustomEvent<PaginationMeta>(META_EVENT, { detail: meta }));
}

function cachedResponse(page: CachedPage) {
  return new Response(JSON.stringify(page.payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function installTabCacheFetchGuard() {
  if (typeof window === "undefined") return;
  const guarded = window as CacheWindow;
  if (guarded.__pdpTabCacheInstalled) return;

  const previousFetch = window.fetch.bind(window);
  guarded.__pdpTabCacheInstalled = true;
  guarded.__pdpTabCachePreviousFetch = previousFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return previousFetch(input, init);
    const original = parsedUrl(requestUrl(input));
    if (!original || original.origin !== window.location.origin) return previousFetch(input, init);

    const isNotice = original.pathname === NOTICE_PATH || original.pathname === RECOMMENDED_PATH;
    const isDirect = original.pathname === DIRECT_PATH;
    if (!isNotice && !isDirect) return previousFetch(input, init);

    const kind: CacheKind = isDirect ? "direct" : "notice";
    const context = currentCacheContext(kind);
    if (!context) return previousFetch(input, init);

    const cache = pageCache();
    const cached = cache.get(context.key);
    if (cached && Date.now() - cached.storedAt <= CACHE_TTL_MS) {
      cache.delete(context.key);
      cache.set(context.key, cached);
      dispatchMeta(cached.meta);
      return cachedResponse(cached);
    }
    if (cached) cache.delete(context.key);

    const response = await previousFetch(input, init);
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;

    try {
      const payload = await response.clone().json() as PaginatedPayload;
      if (!Array.isArray(payload) && Array.isArray(payload.results)) {
        const normalizedPayload = { ...payload, next: null, previous: null };
        const meta: PaginationMeta = {
          ...context.metaBase,
          count: Number(payload.count || 0),
        };
        remember(context.key, { payload: normalizedPayload, meta, storedAt: Date.now() });
        return response;
      }
    } catch {
      return response;
    }
    return response;
  };
}

export default function ProcurementTabCacheEnhancement() {
  installTabCacheFetchGuard();

  useEffect(() => {
    const onSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!detail || detail.source === "pagination") return;
      if (detail.bulkWorkspace) {
        pageCache().clear();
        return;
      }
      if (detail.noticeId) clearKind("notice");
      if (detail.directId) clearKind("direct");
    };

    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
  }, []);

  return null;
}
