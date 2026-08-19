"use client";

import { useEffect } from "react";
import { PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type JsonObject = Record<string, unknown>;
type ManagementWindow = Window & {
  __pdpManagementPerformanceInstalled?: boolean;
  __pdpManagementPreviousFetch?: typeof window.fetch;
  __pdpManagementDashboardCache?: { payload: JsonObject; storedAt: number };
};

const API_PREFIX = "/api/v1/procurement/";
const EXTRACTION_RUNS_PATH = `${API_PREFIX}extraction-runs/`;
const DASHBOARD_PATH = `${API_PREFIX}dashboard/`;
const MANAGEMENT_HISTORY_PAGE_SIZE = 20;
const DASHBOARD_CACHE_TTL_MS = 60 * 1000;

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

function rewrittenInput(input: RequestInfo | URL, url: URL): RequestInfo | URL {
  if (input instanceof Request) return new Request(url.toString(), input);
  if (input instanceof URL) return url;
  return url.toString();
}

function jsonResponse(response: Response, payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: response.status,
    statusText: response.statusText,
    headers: new Headers(response.headers),
  });
}

function cachedDashboardResponse(payload: JsonObject) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function installManagementPerformanceGuard() {
  if (typeof window === "undefined") return;
  const guarded = window as ManagementWindow;
  if (guarded.__pdpManagementPerformanceInstalled) return;

  const previousFetch = window.fetch.bind(window);
  guarded.__pdpManagementPerformanceInstalled = true;
  guarded.__pdpManagementPreviousFetch = previousFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return previousFetch(input, init);
    const original = parsedUrl(requestUrl(input));
    if (!original || original.origin !== window.location.origin) return previousFetch(input, init);

    if (original.pathname === EXTRACTION_RUNS_PATH) {
      const requestedPage = original.searchParams.get("page");
      if (requestedPage && requestedPage !== "1") return previousFetch(input, init);

      const bounded = new URL(original.toString());
      bounded.searchParams.set("page", "1");
      bounded.searchParams.set("page_size", String(MANAGEMENT_HISTORY_PAGE_SIZE));
      const response = await previousFetch(rewrittenInput(input, bounded), init);
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;

      try {
        const payload = await response.clone().json() as JsonObject & { results?: unknown[] };
        if (!Array.isArray(payload) && Array.isArray(payload.results)) {
          return jsonResponse(response, { ...payload, next: null, previous: null });
        }
      } catch {
        return response;
      }
      return response;
    }

    if (original.pathname === DASHBOARD_PATH) {
      const cached = guarded.__pdpManagementDashboardCache;
      if (cached && Date.now() - cached.storedAt <= DASHBOARD_CACHE_TTL_MS) {
        return cachedDashboardResponse(cached.payload);
      }
      if (cached) delete guarded.__pdpManagementDashboardCache;

      const response = await previousFetch(input, init);
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
      try {
        const payload = await response.clone().json() as JsonObject;
        guarded.__pdpManagementDashboardCache = { payload, storedAt: Date.now() };
      } catch {
        return response;
      }
      return response;
    }

    return previousFetch(input, init);
  };
}

export default function ProcurementManagementPerformanceEnhancement() {
  installManagementPerformanceGuard();

  useEffect(() => {
    const onSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!detail || detail.source === "pagination") return;
      delete (window as ManagementWindow).__pdpManagementDashboardCache;
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
  }, []);

  return null;
}
