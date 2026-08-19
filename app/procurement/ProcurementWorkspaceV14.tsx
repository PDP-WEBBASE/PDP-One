"use client";

import { useEffect, useState } from "react";
import FastAnalysisContextManager, { AnalysisSection } from "./FastAnalysisContextManager";
import AnalysisEnginePanel from "./AnalysisEnginePanel";
import ProcurementWorkspaceV13 from "./ProcurementWorkspaceV13";

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
const TRANSIENT_HTTP_STATUSES = new Set([502, 503, 504]);
const FETCH_RECOVERY_ATTEMPTS = 3;
const FETCH_RECOVERY_DELAY_MS = 2_500;

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

function optionalStartupCollection(value: string) {
  const parsed = parsedRequestUrl(value);
  return parsed?.pathname === "/api/v1/procurement/extraction-runs/";
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

function emptyCollectionResponse() {
  return new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
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

async function probeFailedEndpoint(failure: FetchFailure) {
  const guardedWindow = window as GuardWindow;
  const nativeFetch = guardedWindow.__pdpProcurementNativeFetch || window.fetch.bind(window);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await nativeFetch(failure.url, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    return response.ok && (response.headers.get("content-type") || "").includes("application/json");
  } catch {
    return false;
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
    const mayDegrade = method === "GET" && optionalStartupCollection(requestUrl);
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
        if (method === "GET" && TRANSIENT_HTTP_STATUSES.has(response.status)) {
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
          if (mayDegrade) return emptyCollectionResponse();
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
        if (mayDegrade && retryable) return emptyCollectionResponse();
        throw lastError;
      } finally {
        window.clearTimeout(timeout);
        originalSignal?.removeEventListener("abort", abortFromCaller);
      }
    }

    if (mayDegrade) return emptyCollectionResponse();
    throw lastError instanceof Error ? lastError : new Error("procurement-fetch-failed");
  };
}

function failureText(failure: FetchFailure) {
  if (failure.reason === "timeout") return "پاسخ این Endpoint بیش از ۱۰ ثانیه طول کشید";
  if (failure.reason === "service") return `سرویس با خطای موقت ${failure.status || "نامشخص"} پاسخ داد`;
  return "ارتباط شبکه با این Endpoint قطع شد";
}

function failureLead(failure: FetchFailure) {
  return failure.url.startsWith("/api/v1/procurement/extraction-runs/")
    ? "گزارش استخراج موقتاً بارگذاری نشد؛ سایر بخش‌های زیرسامانه فعال‌اند."
    : "بارگذاری زیرسامانه کامل نشد.";
}

export default function ProcurementWorkspaceV14() {
  ensureProcurementFetchGuard();
  const [analysisSection, setAnalysisSection] = useState<AnalysisSection | null>(null);
  const [engineOpen, setEngineOpen] = useState(false);
  const [fetchFailure, setFetchFailure] = useState<FetchFailure | null>(null);
  const [retryingFailure, setRetryingFailure] = useState(false);

  useEffect(() => {
    const handleFailure = (event: Event) => {
      setFetchFailure((event as CustomEvent<FetchFailure>).detail);
    };
    window.addEventListener(FETCH_FAILURE_EVENT, handleFailure);
    return () => window.removeEventListener(FETCH_FAILURE_EVENT, handleFailure);
  }, []);

  useEffect(() => {
    if (!fetchFailure) return;
    let cancelled = false;
    const failure = fetchFailure;

    const recover = async () => {
      for (let attempt = 1; attempt <= FETCH_RECOVERY_ATTEMPTS; attempt += 1) {
        if (attempt > 1) await wait(FETCH_RECOVERY_DELAY_MS);
        if (cancelled) return;
        if (await probeFailedEndpoint(failure)) {
          if (!cancelled) {
            setFetchFailure((current) => current?.url === failure.url && current.at === failure.at ? null : current);
          }
          return;
        }
      }
    };

    const start = window.setTimeout(() => void recover(), FETCH_RECOVERY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(start);
    };
  }, [fetchFailure]);

  const retryFailedEndpoint = async () => {
    if (!fetchFailure || retryingFailure) return;
    const failure = fetchFailure;
    setRetryingFailure(true);
    try {
      if (await probeFailedEndpoint(failure)) {
        setFetchFailure((current) => current?.url === failure.url && current.at === failure.at ? null : current);
      }
    } finally {
      setRetryingFailure(false);
    }
  };

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
        onClick={() => void retryFailedEndpoint()}
        disabled={retryingFailure}
        style={{border:0,borderRadius:8,padding:"7px 11px",background:"#991b1b",color:"white",font:"inherit",fontWeight:700,cursor:retryingFailure?"wait":"pointer",opacity:retryingFailure ? .72 : 1}}
      >
        {retryingFailure ? "در حال بررسی…" : "تلاش مجدد"}
      </button>
    </aside>}
    <button
      type="button"
      data-pdp-analysis-context-manager="true"
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
    {analysisSection && <FastAnalysisContextManager initialSection={analysisSection} onClose={() => setAnalysisSection(null)} />}
    {engineOpen && <AnalysisEnginePanel onClose={() => setEngineOpen(false)} />}
  </>;
}