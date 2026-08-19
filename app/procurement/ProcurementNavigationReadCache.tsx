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
};

const API_PREFIX = "/api/v1/procurement/";
const CACHE_TTL_MS = 5 * 60 * 1000;
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

function clearAll() {
  readCache().clear();
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
    if (mode !== "reload" && mode !== "no-store") {
      const cached = readCache().get(key);
      if (cached && Date.now() - cached.storedAt <= CACHE_TTL_MS) {
        readCache().delete(key);
        readCache().set(key, cached);
        return cachedResponse(cached);
      }
      if (cached) readCache().delete(key);
    }

    const response = await previousFetch(input, init);
    if (mode !== "no-store") void storeJsonResponse(key, response);
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

    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onProcurementSync);
    window.addEventListener(ANALYSIS_CONTEXT_SYNC_EVENT, onAnalysisSync);
    return () => {
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onProcurementSync);
      window.removeEventListener(ANALYSIS_CONTEXT_SYNC_EVENT, onAnalysisSync);
    };
  }, []);

  return null;
}
