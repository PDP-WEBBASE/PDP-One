"use client";

import ProcurementWorkspaceV21 from "./ProcurementWorkspaceV21";

type NoticeRow = {
  id?: string;
  [key: string]: unknown;
};

type CollectionPayload = NoticeRow[] | {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: NoticeRow[];
  [key: string]: unknown;
};

type RecommendedCoverageWindow = Window & {
  __pdpRecommendedCoverageInstalled?: boolean;
  __pdpRecommendedCoverageNativeFetch?: typeof window.fetch;
};

const RECOMMENDED_PAGE_LIMIT = 100;

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function parsedUrl(value: string) {
  try {
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
}

function isNoticeCollection(url: URL | null) {
  return Boolean(url && url.pathname.endsWith("/api/v1/procurement/notices/"));
}

function isWorkspaceRootNoticeRequest(url: URL | null) {
  if (!isNoticeCollection(url)) return false;
  if (url!.searchParams.get("ordering") !== "-last_seen_at") return false;
  if (url!.searchParams.has("page")) return false;
  if (url!.searchParams.has("is_recommended")) return false;
  if (url!.searchParams.has("resolved_notice_type")) return false;
  return true;
}

function isWorkspaceNoticePageRequest(url: URL | null) {
  return Boolean(
    isNoticeCollection(url)
    && url!.searchParams.get("ordering") === "-last_seen_at"
    && url!.searchParams.has("page")
    && !url!.searchParams.has("is_recommended")
  );
}

function mergeUnique(primary: NoticeRow[], extra: NoticeRow[]) {
  const merged: NoticeRow[] = [];
  const seen = new Set<string>();
  for (const item of [...primary, ...extra]) {
    const id = String(item.id || "");
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    merged.push(item);
  }
  return merged;
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

function withoutSignal(init?: RequestInit): RequestInit | undefined {
  if (!init) return init;
  const rest: RequestInit = { ...init };
  delete rest.signal;
  return rest;
}

async function fetchCompleteRecommended(
  nativeFetch: typeof window.fetch,
  root: URL,
  init?: RequestInit,
) {
  const rows: NoticeRow[] = [];
  let next: URL | null = new URL(root.toString());
  next.search = "";
  next.searchParams.set("is_recommended", "true");
  next.searchParams.set("ordering", "-last_seen_at");
  let pages = 0;
  const recommendationInit = withoutSignal(init);

  while (next && pages < RECOMMENDED_PAGE_LIMIT) {
    if (next.origin !== window.location.origin) break;
    const response = await nativeFetch(`${next.pathname}${next.search}`, recommendationInit);
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) break;
    const payload = await response.json() as CollectionPayload;
    if (Array.isArray(payload)) {
      rows.push(...payload);
      break;
    }
    rows.push(...(payload.results || []));
    if (!payload.next) break;
    const candidate = new URL(payload.next, window.location.origin);
    if (candidate.origin !== window.location.origin) break;
    next = candidate;
    pages += 1;
  }
  return rows;
}

function installRecommendedCoverageFetch() {
  if (typeof window === "undefined") return;
  const guardedWindow = window as RecommendedCoverageWindow;
  if (guardedWindow.__pdpRecommendedCoverageInstalled) return;

  const nativeFetch = window.fetch.bind(window);
  guardedWindow.__pdpRecommendedCoverageNativeFetch = nativeFetch;
  guardedWindow.__pdpRecommendedCoverageInstalled = true;

  let rootRequestCount = 0;
  let injectedRecommendationIds = new Set<string>();
  let backgroundCycle = false;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (requestMethod(input, init) !== "GET") return nativeFetch(input, init);
    const url = parsedUrl(requestUrl(input));

    if (isWorkspaceRootNoticeRequest(url)) {
      rootRequestCount += 1;
      // ProcurementWorkspaceV13 deliberately loads the first page first for fast
      // startup, then starts a broader background load. Leave the first request
      // untouched and enrich only the background request with the complete,
      // server-filtered recommended set.
      if (rootRequestCount % 2 === 1) {
        backgroundCycle = false;
        injectedRecommendationIds = new Set<string>();
        return nativeFetch(input, init);
      }

      const baseResponse = await nativeFetch(input, init);
      if (!baseResponse.ok || !(baseResponse.headers.get("content-type") || "").includes("application/json")) {
        return baseResponse;
      }
      try {
        const basePayload = await baseResponse.clone().json() as CollectionPayload;
        const recommended = await fetchCompleteRecommended(nativeFetch, url!, init);
        injectedRecommendationIds = new Set(
          recommended.map((item) => String(item.id || "")).filter(Boolean),
        );
        backgroundCycle = injectedRecommendationIds.size > 0;

        if (Array.isArray(basePayload)) {
          return jsonResponse(baseResponse, mergeUnique(basePayload, recommended));
        }
        return jsonResponse(baseResponse, {
          ...basePayload,
          results: mergeUnique(basePayload.results || [], recommended),
        });
      } catch {
        // Recommendation coverage is additive. If it fails, preserve the normal
        // workspace response instead of turning a non-critical enhancement into
        // a startup failure.
        return baseResponse;
      }
    }

    if (backgroundCycle && isWorkspaceNoticePageRequest(url)) {
      const response = await nativeFetch(input, init);
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) {
        return response;
      }
      try {
        const payload = await response.clone().json() as CollectionPayload;
        if (Array.isArray(payload)) {
          backgroundCycle = false;
          return jsonResponse(response, payload.filter((item) => !injectedRecommendationIds.has(String(item.id || ""))));
        }
        const filtered = (payload.results || []).filter(
          (item) => !injectedRecommendationIds.has(String(item.id || "")),
        );
        if (!payload.next) backgroundCycle = false;
        return jsonResponse(response, { ...payload, results: filtered });
      } catch {
        return response;
      }
    }

    return nativeFetch(input, init);
  };
}

export default function ProcurementWorkspaceV22() {
  installRecommendedCoverageFetch();
  return <ProcurementWorkspaceV21 />;
}
