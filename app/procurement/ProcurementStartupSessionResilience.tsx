"use client";

type StartupSessionWindow = Window & {
  __pdpStartupSessionResilienceInstalled?: boolean;
  __pdpStartupSessionNativeFetch?: typeof window.fetch;
};

const SESSION_PATH = "/api/v1/auth/session/";
const SESSION_ATTEMPT_TIMEOUT_MS = 15_000;
const SESSION_MAX_ATTEMPTS = 2;
const SESSION_RETRY_DELAY_MS = 1_000;

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function normalSessionRequest(input: RequestInfo | URL, init?: RequestInit) {
  if (requestMethod(input, init) !== "GET") return false;
  try {
    const parsed = new URL(requestUrl(input), window.location.origin);
    return parsed.origin === window.location.origin
      && parsed.pathname === SESSION_PATH
      && parsed.searchParams.get("pdp_reset_session") !== "1";
  } catch {
    return false;
  }
}

function installStartupSessionResilience() {
  if (typeof window === "undefined") return;
  const guarded = window as StartupSessionWindow;
  if (guarded.__pdpStartupSessionResilienceInstalled) return;

  const nativeFetch = window.fetch.bind(window);
  guarded.__pdpStartupSessionNativeFetch = nativeFetch;
  guarded.__pdpStartupSessionResilienceInstalled = true;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!normalSessionRequest(input, init)) return nativeFetch(input, init);

    let lastError: unknown = null;
    for (let attempt = 1; attempt <= SESSION_MAX_ATTEMPTS; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), SESSION_ATTEMPT_TIMEOUT_MS);
      try {
        // The procurement fetch guard has its own 10-second signal. Session startup
        // gets this separate bounded window so a transient 11-15 second startup
        // delay is not misreported as a fatal subsystem outage. The native request
        // is still hard-bounded here and ordinary procurement endpoints keep the
        // existing 10-second protection.
        return await nativeFetch(input, {
          ...init,
          cache: "no-store",
          signal: controller.signal,
        });
      } catch (error) {
        lastError = error;
        if (attempt < SESSION_MAX_ATTEMPTS) await wait(SESSION_RETRY_DELAY_MS);
      } finally {
        window.clearTimeout(timeout);
      }
    }

    throw lastError instanceof Error ? lastError : new Error("startup-session-unavailable");
  };
}

export default function ProcurementStartupSessionResilience() {
  installStartupSessionResilience();
  return null;
}
