"use client";

import { useEffect, useState } from "react";

type Metrics = {
  notice_total: number;
  unanalyzed: number;
  recommended: number;
  selected: number;
  submitted: number;
  urgent: number;
  won: number;
  lost: number;
  win_rate: number;
};

type CollectionPayload = {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

type IntegrityWindow = Window & {
  __pdpPublicationCompatibilityInstalled?: boolean;
};

const fa = new Intl.NumberFormat("fa-IR");
const RECENT_LABELS = new Set(["مناقصات ۳ روز اخیر", "استعلامات ۳ روز اخیر"]);

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function activeRecentLabel() {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((candidate) =>
    RECENT_LABELS.has(normalize(candidate.textContent)) && Boolean(normalize(candidate.className)),
  );
  return normalize(button?.textContent);
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit) {
  return (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
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

function installPublicationDateCompatibility() {
  if (typeof window === "undefined") return;
  const guarded = window as IntegrityWindow;
  if (guarded.__pdpPublicationCompatibilityInstalled) return;
  guarded.__pdpPublicationCompatibilityInstalled = true;
  const innerFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await innerFetch(input, init);
    if (requestMethod(input, init) !== "GET" || !RECENT_LABELS.has(activeRecentLabel())) return response;
    let url: URL;
    try {
      url = new URL(requestUrl(input), window.location.origin);
    } catch {
      return response;
    }
    if (!url.pathname.endsWith("/api/v1/procurement/notices/")) return response;
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return response;
    try {
      const payload = await response.clone().json() as CollectionPayload;
      if (!Array.isArray(payload.results)) return response;
      return jsonResponse(response, {
        ...payload,
        results: payload.results.map((item) => {
          const publishedDate = String(item.published_date || "").trim();
          if (!publishedDate) return item;
          // V13's legacy recent predicate reads first_seen_at. The server already
          // selected the three-day set by published_date; this response-only
          // compatibility value keeps that legacy predicate from discarding a
          // valid server-selected row. PostgreSQL/source data is not changed.
          return { ...item, first_seen_at: `${publishedDate}T00:00:00+03:30` };
        }),
      });
    } catch {
      return response;
    }
  };
}

function findPanel(title: string) {
  return Array.from(document.querySelectorAll<HTMLElement>("article")).find((article) =>
    normalize(article.querySelector("h2")?.textContent) === title,
  ) || null;
}

function setText(node: Element | null, value: string) {
  if (node && normalize(node.textContent) !== normalize(value)) node.textContent = value;
}

function setKpi(label: string, value: number) {
  const article = Array.from(document.querySelectorAll<HTMLElement>("article")).find((candidate) =>
    normalize(candidate.querySelector("span")?.textContent) === label,
  );
  setText(article?.querySelector("b") || null, fa.format(value));
}

function setPrefixedSpan(panel: HTMLElement | null, prefix: string, value: number, suffix = "") {
  const span = Array.from(panel?.querySelectorAll("span") || []).find((candidate) =>
    normalize(candidate.textContent).startsWith(prefix),
  );
  setText(span || null, `${prefix} ${fa.format(value)}${suffix}`);
}

function patchDashboard(metrics: Metrics) {
  const dashboardButton = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
    normalize(button.textContent) === "داشبورد مدیریتی" && Boolean(normalize(button.className)),
  );
  if (!dashboardButton) return;

  setKpi("تحلیل‌نشده", metrics.unanalyzed);
  setKpi("پیشنهادی", metrics.recommended);
  setKpi("منتخب", metrics.selected);
  setKpi("ارسال‌شده", metrics.submitted);
  setKpi("نزدیک مهلت", metrics.urgent);
  setKpi("نتیجه موفق", metrics.won);

  const alerts = findPanel("هشدارهای مدیریتی");
  const urgentAlert = Array.from(alerts?.querySelectorAll("span") || []).find((span) =>
    normalize(span.textContent).endsWith("پرونده نزدیک به مهلت"),
  );
  setText(urgentAlert || null, `${fa.format(metrics.urgent)} پرونده نزدیک به مهلت`);

  const funnel = findPanel("قیف مدیریتی");
  setPrefixedSpan(funnel, "استخراج و ثبت‌شده", metrics.notice_total);
  setPrefixedSpan(funnel, "پیشنهادی", metrics.recommended);
  setPrefixedSpan(funnel, "منتخب", metrics.selected);
  setPrefixedSpan(funnel, "ارسال‌شده", metrics.submitted);
  setPrefixedSpan(funnel, "نتیجه موفق", metrics.won);

  const outcome = findPanel("برد و باخت");
  for (const label of ["موفق", "ناموفق", "نرخ موفقیت"]) {
    const labelNode = Array.from(outcome?.querySelectorAll("span") || []).find((span) => normalize(span.textContent) === label);
    const valueNode = labelNode?.parentElement?.querySelector("b") || null;
    if (label === "موفق") setText(valueNode, fa.format(metrics.won));
    else if (label === "ناموفق") setText(valueNode, fa.format(metrics.lost));
    else setText(valueNode, `${fa.format(metrics.win_rate)}٪`);
  }

  const summary = findPanel("جمع‌بندی مدیریتی ChatGPT");
  setText(
    summary?.querySelector("p") || null,
    `${fa.format(metrics.notice_total)} فراخوان واقعی در پایگاه‌داده موجود است. ${fa.format(metrics.urgent)} مورد دارای فوریت زیاد یا بحرانی است.`,
  );
  setPrefixedSpan(summary, "داده واقعی:", metrics.notice_total);
  setPrefixedSpan(summary, "نیازمند تصمیم:", metrics.recommended);
  setPrefixedSpan(summary, "فوریت بالا:", metrics.urgent);
}

export default function ProcurementPaginationIntegrityEnhancement() {
  installPublicationDateCompatibility();
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      void fetch("/api/v1/procurement/pagination-dashboard-metrics/", {
        credentials: "include",
        headers: { Accept: "application/json" },
      }).then(async (response) => {
        if (!response.ok) throw new Error(`metrics-${response.status}`);
        return await response.json() as Metrics;
      }).then((payload) => {
        if (active) setMetrics(payload);
      }).catch(() => undefined);
    };
    load();
    window.addEventListener("pdp-procurement-ui-sync", load);
    return () => {
      active = false;
      window.removeEventListener("pdp-procurement-ui-sync", load);
    };
  }, []);

  useEffect(() => {
    if (!metrics) return;
    let scheduled = false;
    const apply = () => {
      scheduled = false;
      patchDashboard(metrics);
    };
    const observer = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(apply);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"] });
    patchDashboard(metrics);
    return () => observer.disconnect();
  }, [metrics]);

  return null;
}
