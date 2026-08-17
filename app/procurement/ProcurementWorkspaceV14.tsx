"use client";

import { useEffect, useState } from "react";
import AnalysisContextManager from "./AnalysisContextManager";
import AnalysisEnginePanel from "./AnalysisEnginePanel";
import ProcurementWorkspaceV13 from "./ProcurementWorkspaceV13";

type AnalysisSection = "prompts" | "keywords" | "company" | "versions";
type FetchFailure = {
  url: string;
  reason: "timeout" | "network" | "service";
  status?: number;
  at: number;
};

type GuardWindow = Window & {
  __pdpProcurementFetchGuardInstalled?: boolean;
  __pdpProcurementNativeFetch?: typeof window.fetch;
};

const FETCH_FAILURE_EVENT = "pdp-procurement-fetch-failure";
const RECOVERABLE_HTTP_STATUSES = new Set([500, 502, 503, 504]);
const AUTOMATION_SETTINGS_PATH = "/api/v1/procurement/automation-settings/";
const MANAGEMENT_COLLECTION_PATHS = new Set([
  "/api/v1/procurement/extraction-runs/",
  "/api/v1/procurement/sources/",
  AUTOMATION_SETTINGS_PATH,
]);

const labelToSection: Record<string, AnalysisSection> = {
  "نقش و Prompt": "prompts",
  "کلیدواژه‌ها": "keywords",
  "پروفایل، صلاحیت و رزومه": "company",
  "نسخه‌ها و فعال‌سازی": "versions",
};

const floatingButtonStyle = {
  position: "fixed",
  zIndex: 800,
  border: "1px solid rgba(15,118,110,.35)",
  borderRadius: 999,
  color: "white",
  padding: "10px 14px",
  font: "inherit",
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 12px 28px rgba(15,23,42,.2)",
} as const;

function parsedRequestUrl(value: string) {
  try {
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
}

function guardedRequestUrl(value: string) {
  const parsed = parsedRequestUrl(value);
  return Boolean(parsed && (parsed.pathname.startsWith("/api/v1/procurement/") || parsed.pathname === "/api/v1/auth/session/"));
}

function sessionRequest(value: string) {
  return parsedRequestUrl(value)?.pathname === "/api/v1/auth/session/";
}

function automationSettingsCollection(value: string) {
  return parsedRequestUrl(value)?.pathname === AUTOMATION_SETTINGS_PATH;
}

// Management collections must be independently recoverable. A slow extraction
// history or a transient source/settings endpoint must not blank the other
// management panels or make the schedule editor unusable.
function optionalManagementCollection(value: string) {
  const parsed = parsedRequestUrl(value);
  return Boolean(parsed && MANAGEMENT_COLLECTION_PATHS.has(parsed.pathname));
}

function displayRequestUrl(value: string) {
  const parsed = parsedRequestUrl(value);
  return parsed ? `${parsed.pathname}${parsed.search}` : value;
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

function emitFetchFailure(detail: FetchFailure) {
  window.dispatchEvent(new CustomEvent<FetchFailure>(FETCH_FAILURE_EVENT, { detail }));
}

function defaultAutomationSettings() {
  return {
    id: "default",
    key: "default",
    enabled: false,
    cadence: "daily",
    interval_minutes: 60,
    daily_time: "11:00:00",
    timezone_name: "Asia/Tehran",
    analysis_delay_minutes: 0,
    scheduled_task_enabled: true,
    next_extraction_at: null,
  };
}

function fallbackCollectionResponse(requestUrl: string) {
  const results = automationSettingsCollection(requestUrl) ? [defaultAutomationSettings()] : [];
  return new Response(JSON.stringify({ count: results.length, next: null, previous: null, results }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function normalizeAutomationSettingsResponse(response: Response) {
  try {
    const payload = await response.clone().json() as unknown;
    const normalize = (item: Record<string, unknown>) => ({
      ...item,
      daily_time: item.daily_time || "11:00:00",
      timezone_name: item.timezone_name || "Asia/Tehran",
    });

    if (Array.isArray(payload)) {
      const normalized = payload.length
        ? payload.map((item) => normalize(item as Record<string, unknown>))
        : [defaultAutomationSettings()];
      return new Response(JSON.stringify(normalized), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    }

    if (payload && typeof payload === "object" && Array.isArray((payload as { results?: unknown[] }).results)) {
      const collection = payload as { results: unknown[]; [key: string]: unknown };
      const results = collection.results.length
        ? collection.results.map((item) => normalize(item as Record<string, unknown>))
        : [defaultAutomationSettings()];
      return new Response(JSON.stringify({ ...collection, count: results.length, results }), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    }
  } catch {
    return response;
  }
  return response;
}

async function recoverBrowserSession(nativeFetch: typeof window.fetch) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await nativeFetch("/api/v1/auth/session/?pdp_reset_session=1", {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "X-PDP-Reset-Session": "1",
      },
      signal: controller.signal,
    });
    if (!response.ok || response.headers.get("X-PDP-Session-Recovered") !== "1") {
      throw new Error(`session-recovery-${response.status}`);
    }
    return response;
  } finally {
    window.clearTimeout(timeout);
  }
}

function ensureProcurementFetchGuard() {
  if (typeof window === "undefined") return;
  const guardedWindow = window as GuardWindow;
  if (guardedWindow.__pdpProcurementFetchGuardInstalled) return;

  const nativeFetch = window.fetch.bind(window);
  guardedWindow.__pdpProcurementNativeFetch = nativeFetch;
  guardedWindow.__pdpProcurementFetchGuardInstalled = true;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const requestUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (!guardedRequestUrl(requestUrl)) return nativeFetch(input, init);

    const method = (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    const isSessionRequest = method === "GET" && sessionRequest(requestUrl);
    const maxAttempts = isSessionRequest ? 1 : method === "GET" ? 2 : 1;
    const mayDegrade = method === "GET" && optionalManagementCollection(requestUrl);
    let lastError: unknown = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const controller = new AbortController();
      const originalSignal = init?.signal || (input instanceof Request ? input.signal : undefined);
      const abortFromCaller = () => controller.abort();
      let timedOut = false;

      if (originalSignal) {
        if (originalSignal.aborted) controller.abort();
        else originalSignal.addEventListener("abort", abortFromCaller, { once: true });
      }

      const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, 10_000);

      try {
        const response = await nativeFetch(input, { ...init, signal: controller.signal });
        if (method === "GET" && RECOVERABLE_HTTP_STATUSES.has(response.status)) {
          if (attempt < maxAttempts) {
            await wait(1_500);
            continue;
          }
          emitFetchFailure({
            url: displayRequestUrl(requestUrl),
            reason: "service",
            status: response.status,
            at: Date.now(),
          });
          if (mayDegrade) return fallbackCollectionResponse(requestUrl);
        }
        if (method === "GET" && automationSettingsCollection(requestUrl) && response.ok) {
          return normalizeAutomationSettingsResponse(response);
        }
        return response;
      } catch (error) {
        lastError = error;
        const retryable = method === "GET" && (timedOut || error instanceof TypeError);
        if (retryable && attempt < maxAttempts) {
          await wait(1_500);
          continue;
        }
        if (isSessionRequest && retryable) {
          try {
            return await recoverBrowserSession(nativeFetch);
          } catch (recoveryError) {
            lastError = recoveryError;
          }
        }
        emitFetchFailure({
          url: displayRequestUrl(requestUrl),
          reason: timedOut ? "timeout" : "network",
          at: Date.now(),
        });
        if (mayDegrade && retryable) return fallbackCollectionResponse(requestUrl);
        throw lastError;
      } finally {
        window.clearTimeout(timeout);
        originalSignal?.removeEventListener("abort", abortFromCaller);
      }
    }

    if (mayDegrade) return fallbackCollectionResponse(requestUrl);
    throw lastError instanceof Error ? lastError : new Error("procurement-fetch-failed");
  };
}

function failureText(failure: FetchFailure) {
  if (failure.reason === "timeout") return "پاسخ این Endpoint بیش از ۱۰ ثانیه طول کشید";
  if (failure.reason === "service") return `سرویس با خطای موقت ${failure.status || "نامشخص"} پاسخ داد`;
  return "ارتباط شبکه با این Endpoint قطع شد";
}

function failureLead(failure: FetchFailure) {
  return optionalManagementCollection(failure.url)
    ? "بخشی از اطلاعات مدیریت موقتاً بارگذاری نشد؛ سایر تنظیمات و عملیات قابل استفاده‌اند."
    : "بارگذاری زیرسامانه کامل نشد.";
}

export default function ProcurementWorkspaceV14() {
  ensureProcurementFetchGuard();
  const [analysisSection, setAnalysisSection] = useState<AnalysisSection | null>(null);
  const [engineOpen, setEngineOpen] = useState(false);
  const [fetchFailure, setFetchFailure] = useState<FetchFailure | null>(null);

  useEffect(() => {
    if (analysisSection) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const button = target?.closest("button");
      if (!button) return;
      const section = labelToSection[(button.textContent || "").trim()];
      if (!section) return;
      setAnalysisSection(section);
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [analysisSection]);

  useEffect(() => {
    const handleFailure = (event: Event) => {
      setFetchFailure((event as CustomEvent<FetchFailure>).detail);
    };
    window.addEventListener(FETCH_FAILURE_EVENT, handleFailure);
    return () => window.removeEventListener(FETCH_FAILURE_EVENT, handleFailure);
  }, []);

  return <>
    <ProcurementWorkspaceV13 />
    {fetchFailure && <aside
      role="alert"
      dir="rtl"
      style={{
        position: "fixed",
        zIndex: 1200,
        insetInline: 20,
        top: 14,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        flexWrap: "wrap",
        padding: "10px 14px",
        border: "1px solid #f3a59a",
        borderRadius: 12,
        background: "#fff1ef",
        color: "#7f1d1d",
        boxShadow: "0 14px 34px rgba(15,23,42,.18)",
        fontSize: 13,
      }}
    >
      <span><b>{failureLead(fetchFailure)}</b> {failureText(fetchFailure)}: <code dir="ltr">{fetchFailure.url}</code></span>
      <button
        type="button"
        onClick={() => window.location.reload()}
        style={{border:0,borderRadius:8,padding:"7px 11px",background:"#991b1b",color:"white",font:"inherit",fontWeight:700,cursor:"pointer"}}
      >
        تلاش مجدد
      </button>
    </aside>}
    <button
      type="button"
      onClick={() => setAnalysisSection("prompts")}
      style={{
        ...floatingButtonStyle,
        insetInlineStart: 20,
        bottom: 20,
        background: "#0f766e",
      }}
    >
      تنظیمات تحلیل واقعی
    </button>
    <button
      type="button"
      onClick={() => setEngineOpen(true)}
      style={{
        ...floatingButtonStyle,
        insetInlineStart: 20,
        bottom: 70,
        background: "#1d4ed8",
        borderColor: "rgba(29,78,216,.35)",
      }}
    >
      موتور تحلیل PDP
    </button>
    {analysisSection && <AnalysisContextManager initialSection={analysisSection} onClose={() => setAnalysisSection(null)} />}
    {engineOpen && <AnalysisEnginePanel onClose={() => setEngineOpen(false)} />}
  </>;
}