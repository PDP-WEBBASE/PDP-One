"use client";

import { useEffect } from "react";
import { ANALYSIS_CONTEXT_SYNC_EVENT } from "./analysisContextSync";
import { PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type StoredResponse = {
  body: string;
  status: number;
  statusText: string;
  headers: [string, string][];
  storedAt: number;
};

type CacheWindow = Window & {
  __pdpNavigationReadCacheInstalled?: boolean;
  __pdpNavigationReadPreviousFetch?: typeof window.fetch;
  __pdpNavigationReadCache?: Map<string, StoredResponse>;
  __pdpNavigationReadRevalidating?: Set<string>;
  __pdpNavigationForceRefreshUntil?: number;
  __pdpTabPageCache?: Map<string, unknown>;
  __pdpManagementDashboardCache?: unknown;
};

const API_PREFIX = "/api/v1/procurement/";
const CACHE_REVALIDATE_MS = 5 * 60 * 1000;
const DYNAMIC_REVALIDATE_MS = 60 * 1000;
const FORCE_REFRESH_WINDOW_MS = 2000;
const MAX_CACHE_ENTRIES = 80;
const MAX_ENTRY_BYTES = 2 * 1024 * 1024;
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const SPECIALIZED_LIST_PATHS = new Set([
  `${API_PREFIX}notices/`,
  `${API_PREFIX}recommended-notices/`,
  `${API_PREFIX}direct-opportunities/`,
  `${API_PREFIX}extraction-runs/`,
  `${API_PREFIX}dashboard/`,
]);
const DYNAMIC_PATH_MARKERS = [
  "/analysis-requests/",
  "/analysis-drafts/",
  "/analysis/review-summary/",
  "/analysis/context/manifest/",
  "/management-dashboard/",
  "/run-status/",
  "/runs/",
];
const REFRESH_LABEL = /(بازخوانی|تازه\s*سازی|به\s*روزرسانی|تلاش مجدد|refresh)/i;

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestCacheMode(input: RequestInfo | URL, init?: RequestInit) {
  return init?.cache || (input instanceof Request ? input.cache : "default");
}

function parsedUrl(value: string) {
  try {
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
}

function readCache() {
  const guarded = window as CacheWindow;
  if (!guarded.__pdpNavigationReadCache) guarded.__pdpNavigationReadCache = new Map();
  return guarded.__pdpNavigationReadCache;
}

function revalidatingKeys() {
  const guarded = window as CacheWindow;
  if (!guarded.__pdpNavigationReadRevalidating) guarded.__pdpNavigationReadRevalidating = new Set();
  return guarded.__pdpNavigationReadRevalidating;
}

function clearAll() {
  readCache().clear();
}

function clearAllNavigationCaches() {
  const guarded = window as CacheWindow;
  clearAll();
  guarded.__pdpTabPageCache?.clear();
  delete guarded.__pdpManagementDashboardCache;
}

function clearAnalysisContextEntries() {
  const cache = readCache();
  for (const key of Array.from(cache.keys())) {
    if (key.includes("/analysis/context/") || key.includes("/analysis-contexts/")) cache.delete(key);
  }
}

function remember(key: string, value: StoredResponse) {
  const cache = readCache();
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value as string | undefined;
    if (!oldest) break;
    cache.delete(oldest);
  }
}

function touch(key: string, value: StoredResponse) {
  const cache = readCache();
  cache.delete(key);
  cache.set(key, value);
}

function cachedResponse(entry: StoredResponse) {
  return new Response(entry.body, {
    status: entry.status,
    statusText: entry.statusText,
    headers: new Headers(entry.headers),
  });
}

function isCacheableProcurementGet(url: URL) {
  return url.origin === window.location.origin
    && url.pathname.startsWith(API_PREFIX)
    && !SPECIALIZED_LIST_PATHS.has(url.pathname);
}

function revalidateAfter(pathname: string) {
  return DYNAMIC_PATH_MARKERS.some((marker) => pathname.includes(marker)) ? DYNAMIC_REVALIDATE_MS : CACHE_REVALIDATE_MS;
}

function forceRefreshActive() {
  return Date.now() <= ((window as CacheWindow).__pdpNavigationForceRefreshUntil || 0);
}

async function storeJsonResponse(key: string, response: Response) {
  if (!response.ok) return;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return;
  const contentLength = Number(response.headers.get("content-length") || 0);
  if (contentLength > MAX_ENTRY_BYTES) return;
  try {
    const body = await response.clone().text();
    if (body.length > MAX_ENTRY_BYTES) return;
    remember(key, {
      body,
      status: response.status,
      statusText: response.statusText,
      headers: Array.from(response.headers.entries()),
      storedAt: Date.now(),
    });
  } catch {
    // A failed cache write must never affect the real response.
  }
}

function revalidateInBackground(
  key: string,
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  previousFetch: typeof window.fetch,
) {
  const active = revalidatingKeys();
  if (active.has(key)) return;
  active.add(key);
  void previousFetch(input, init)
    .then((response) => storeJsonResponse(key, response))
    .catch(() => undefined)
    .finally(() => active.delete(key));
}

function installNavigationReadCache() {
  if (typeof window === "undefined") return;
  const guarded = window as CacheWindow;
  if (guarded.__pdpNavigationReadCacheInstalled) return;

  const previousFetch = window.fetch.bind(window);
  guarded.__pdpNavigationReadCacheInstalled = true;
  guarded.__pdpNavigationReadPreviousFetch = previousFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = requestMethod(input, init);
    const original = parsedUrl(requestUrl(input));
    if (!original || original.origin !== window.location.origin) return previousFetch(input, init);

    if (MUTATING_METHODS.has(method)) {
      const response = await previousFetch(input, init);
      if (response.ok && original.pathname.startsWith(API_PREFIX)) clearAll();
      return response;
    }

    if (method !== "GET" || !isCacheableProcurementGet(original)) return previousFetch(input, init);

    const key = original.toString();
    const mode = requestCacheMode(input, init);
    const forceRefresh = mode === "reload" || forceRefreshActive();
    if (!forceRefresh) {
      const cached = readCache().get(key);
      if (cached) {
        touch(key, cached);
        if (Date.now() - cached.storedAt > revalidateAfter(original.pathname)) {
          revalidateInBackground(key, input, init, previousFetch);
        }
        return cachedResponse(cached);
      }
    }

    const response = await previousFetch(input, init);
    void storeJsonResponse(key, response);
    return response;
  };
}

export default function ProcurementNavigationReadCache() {
  installNavigationReadCache();

  useEffect(() => {
    const onProcurementSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!detail || detail.source === "pagination") return;
      clearAll();
    };
    const onAnalysisSync = () => clearAnalysisContextEntries();
    const onClickCapture = (event: MouseEvent) => {
      const button = (event.target as HTMLElement | null)?.closest("button");
      if (!button || !REFRESH_LABEL.test((button.textContent || "").trim())) return;
      (window as CacheWindow).__pdpNavigationForceRefreshUntil = Date.now() + FORCE_REFRESH_WINDOW_MS;
      clearAllNavigationCaches();
    };

    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onProcurementSync);
    window.addEventListener(ANALYSIS_CONTEXT_SYNC_EVENT, onAnalysisSync);
    document.addEventListener("click", onClickCapture, true);
    return () => {
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onProcurementSync);
      window.removeEventListener(ANALYSIS_CONTEXT_SYNC_EVENT, onAnalysisSync);
      document.removeEventListener("click", onClickCapture, true);
    };
  }, []);

  return null;
}
