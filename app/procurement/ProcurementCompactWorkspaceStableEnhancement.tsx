"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";
import {
  getProcurementStableViewState,
  PROCUREMENT_STABLE_VIEW_STATE_EVENT,
  stableTopLabel,
  stableWorkflowLabel,
} from "./procurementStableViewState";

type SourceBadge = { key: string; name: string; source_url: string; detail_url: string };
type CompactNotice = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  published_date: string | null;
  submission_deadline: string | null;
  source_name: string;
  source_url: string;
  detail_url: string;
  sources: SourceBadge[];
  business_opportunity_type_label?: string;
  activity_domain_label?: string;
  [key: string]: unknown;
};
type NoticePayload = { count: number; page: number; page_size: number; results: CompactNotice[] };
type CountBreakdown = { total: number; tender: number; inquiry: number };
type DashboardPayload = {
  generated_at: string;
  metrics: {
    all_notices: CountBreakdown;
    new_today: CountBreakdown;
    analysis_remaining: CountBreakdown;
    recommended: CountBreakdown;
    selected: CountBreakdown;
    submitted: CountBreakdown;
    near_deadline: CountBreakdown;
    successful_results: CountBreakdown;
  };
  management: { overdue_actions: number; without_responsible: number; direct_active: number };
  analysis: { basis: string; run_id: string | null; run_status: string | null };
};
type SourcePayload = Array<{ name: string; key?: string }> | { results?: Array<{ name: string; key?: string }> };
type CompactWindow = Window & {
  __pdpPaginationPage?: number;
  __pdpCompactDeadlineStatus?: string;
  __pdpCompactPublishedOn?: string;
  __pdpStableListCache?: Map<string, unknown>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const COMPACT_DASHBOARD_PATH = `${PROCUREMENT_API}/ui/dashboard/`;
const BULK_DISMISS_PATH = `${PROCUREMENT_API}/ui/recommendations/dismiss-bulk/`;
const DATA_EVENT = "pdp-procurement-compact-notice-data";
const FILTER_HOST_ID = "pdp-procurement-compact-filter-host";
const DASHBOARD_HOST_ID = "pdp-procurement-compact-dashboard-host";
const LONG_TITLE_THRESHOLD = 220;
const fa = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" });
const faDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" });

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function activeTopTab() {
  return stableTopLabel();
}

function activeWorkflow() {
  return stableWorkflowLabel();
}

function findWorkflowSection() {
  const state = getProcurementStableViewState();
  if (state.top !== "tenders" && state.top !== "inquiries" && state.top !== "direct") return null;
  const expected = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((candidate) =>
    !candidate.closest("nav") && normalize(candidate.textContent) === expected,
  );
  return button?.closest("section") || null;
}

function ensureFilterHost() {
  const top = activeTopTab();
  if (top !== "مناقصات" && top !== "استعلامات") return null;
  const section = findWorkflowSection();
  if (!section) return null;
  const searchLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) =>
    normalize(label.textContent).startsWith("جست‌وجو"),
  );
  const bar = searchLabel?.parentElement;
  if (!bar) return null;
  let host = bar.querySelector<HTMLElement>(`#${FILTER_HOST_ID}`);
  if (!host) {
    host = document.createElement("div");
    host.id = FILTER_HOST_ID;
    host.style.display = "contents";
    bar.appendChild(host);
  }
  return host;
}

function hideLiveDatabaseBanner() {
  const label = Array.from(document.querySelectorAll("b")).find((node) => normalize(node.textContent) === "داده واقعی");
  const banner = label?.parentElement as HTMLElement | null;
  if (banner && normalize(banner.textContent).includes("PostgreSQL")) banner.style.display = "none";
}

function ensureDashboardHost() {
  if (getProcurementStableViewState().top !== "dashboard") return null;
  hideLiveDatabaseBanner();
  const kpiArticle = Array.from(document.querySelectorAll<HTMLElement>("article")).find((article) =>
    Array.from(article.querySelectorAll("span")).some((span) => normalize(span.textContent) === "فراخوان جدید"),
  );
  const kpiContainer = kpiArticle?.parentElement as HTMLElement | null;
  if (!kpiContainer) return null;
  kpiContainer.style.display = "none";
  const dashboardSection = kpiContainer.closest("section");
  if (!dashboardSection) return null;
  const alertHeading = Array.from(dashboardSection.querySelectorAll("h2")).find((heading) => normalize(heading.textContent) === "هشدارهای مدیریتی");
  const oldGrid = alertHeading?.closest("article")?.parentElement as HTMLElement | null;
  if (oldGrid) oldGrid.style.display = "none";
  let host = dashboardSection.querySelector<HTMLElement>(`#${DASHBOARD_HOST_ID}`);
  if (!host) {
    host = document.createElement("div");
    host.id = DASHBOARD_HOST_ID;
    dashboardSection.insertBefore(host, kpiContainer);
  }
  return host;
}

function ensureSourceOptions(sourceNames: string[]) {
  const section = findWorkflowSection();
  if (!section) return;
  const sourceLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("منبع"));
  const select = sourceLabel?.querySelector<HTMLSelectElement>("select");
  if (!select) return;
  const existing = new Set(Array.from(select.options).map((option) => option.value));
  sourceNames.forEach((name) => {
    if (!name || existing.has(name)) return;
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
    existing.add(name);
  });
}

function sourceRank(value: string) {
  const token = value.toLocaleLowerCase("fa");
  if (token.includes("setad") || token.includes("ستاد")) return 0;
  if (token.includes("hezareh") || token.includes("هزاره")) return 1;
  if (token.includes("parsnamad") || token.includes("پارس")) return 2;
  return 3;
}

function sourceSort(a: SourceBadge, b: SourceBadge) {
  return sourceRank(a.name) - sourceRank(b.name) || a.name.localeCompare(b.name, "fa");
}

function deadlineInfo(value: string | null) {
  if (!value) return { remaining: "مهلت نامشخص", date: "تاریخ مهلت نامشخص" };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { remaining: "مهلت نامشخص", date: value };
  const hours = Math.ceil((date.getTime() - Date.now()) / 3600000);
  const remaining = hours < 0 ? "منقضی شده" : hours < 24 ? `${fa.format(hours)} ساعت باقی‌مانده` : `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`;
  return { remaining, date: `مهلت: ${faDate.format(date)}` };
}

function createChip(text: string, className = "pdp-compact-chip") {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = text;
  return node;
}

function createSourceLink(source: SourceBadge, index: number) {
  const node = document.createElement("a");
  node.className = `pdp-compact-source pdp-source-${Math.min(index, 2)}`;
  node.textContent = source.name;
  node.href = source.detail_url || source.source_url || "#";
  node.target = "_blank";
  node.rel = "noreferrer";
  return node;
}

function findArticleForItem(section: HTMLElement, item: CompactNotice) {
  const identified = Array.from(section.querySelectorAll<HTMLElement>("article[data-pdp-notice-id]")).find(
    (article) => article.dataset.pdpNoticeId === item.id,
  );
  if (identified) return identified;
  const title = normalize(item.title);
  return Array.from(section.querySelectorAll<HTMLElement>("article")).find((article) => {
    const heading = normalize(article.querySelector("h3")?.textContent);
    return heading === title || (heading.length > 12 && (title.startsWith(heading.replace(/…$/, "")) || heading.startsWith(title)));
  }) || null;
}

function enhanceRecordCards(payload: NoticePayload | null) {
  if (!payload) return;
  const state = getProcurementStableViewState();
  if (state.top !== "tenders" && state.top !== "inquiries") return;
  const section = findWorkflowSection();
  if (!section) return;

  payload.results.forEach((item) => {
    const article = findArticleForItem(section, item);
    if (!article) return;
    article.classList.add("pdp-compact-record");
    const heading = article.querySelector<HTMLElement>("h3");
    if (heading) {
      heading.classList.add("pdp-full-title");
      heading.classList.toggle("pdp-full-title-long", normalize(item.title).length > LONG_TITLE_THRESHOLD);
    }

    Array.from(article.querySelectorAll<HTMLElement>("span,small")).forEach((node) => {
      const text = normalize(node.textContent);
      if (text.startsWith("پردازش:") || text === item.province || text.includes("باقی‌مانده") || text.includes("گذشته")) node.style.display = "none";
    });

    const sources = [...(item.sources || [])].sort(sourceSort);
    const deadline = deadlineInfo(item.submission_deadline);
    const signature = JSON.stringify([
      sources.map((source) => [source.key, source.name, source.source_url, source.detail_url]),
      item.province,
      deadline.remaining,
      deadline.date,
      item.business_opportunity_type_label,
      item.activity_domain_label,
    ]);
    if (article.dataset.pdpCompactSignature === signature) return;
    article.dataset.pdpCompactSignature = signature;

    article.querySelector("[data-pdp-compact-badges='1']")?.remove();
    const group = document.createElement("div");
    group.dataset.pdpCompactBadges = "1";
    group.className = "pdp-compact-badge-group";
    sources.forEach((source, index) => group.appendChild(createSourceLink(source, index)));
    if (item.business_opportunity_type_label) group.appendChild(createChip(item.business_opportunity_type_label, "pdp-compact-chip pdp-preview-classification-badge"));
    if (item.activity_domain_label) group.appendChild(createChip(item.activity_domain_label, "pdp-compact-chip pdp-preview-classification-badge"));
    if (item.sources.length > 1) group.appendChild(createChip(`${fa.format(item.sources.length)} منبع`, "pdp-compact-chip pdp-source-count"));
    if (item.province) group.appendChild(createChip(item.province));
    group.appendChild(createChip(deadline.remaining));
    group.appendChild(createChip(deadline.date, "pdp-compact-chip pdp-deadline-date"));
    heading?.insertAdjacentElement("afterend", group);

    const dismiss = Array.from(article.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === "حذف از پیشنهادی");
    dismiss?.classList.add("pdp-compact-dismiss");
  });
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("session-unavailable");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function DashboardMetric({ label, value }: { label: string; value: CountBreakdown }) {
  return <div className="pdp-compact-metric"><span>{label}</span><b>{fa.format(value.total)}</b><small><em>مناقصه {fa.format(value.tender)}</em><em>استعلام {fa.format(value.inquiry)}</em></small></div>;
}

function DashboardBox({ data }: { data: DashboardPayload }) {
  return <section className="pdp-compact-dashboard-box">
    <div className="pdp-compact-dashboard-heading"><div><h2>شاخص‌های مدیریتی</h2><small>محاسبه مستقیم سمت سرور؛ تفکیک مناقصه و استعلام</small></div><small>{faDateTime.format(new Date(data.generated_at))}</small></div>
    <div className="pdp-compact-dashboard-metrics">
      <DashboardMetric label="کل فراخوان‌ها" value={data.metrics.all_notices}/><DashboardMetric label="فراخوان جدید امروز" value={data.metrics.new_today}/>
      <DashboardMetric label="تحلیل‌نشده" value={data.metrics.analysis_remaining}/><DashboardMetric label="پیشنهادی" value={data.metrics.recommended}/>
      <DashboardMetric label="منتخب" value={data.metrics.selected}/><DashboardMetric label="ارسال‌شده" value={data.metrics.submitted}/>
      <DashboardMetric label="مهلت تا ۷ روز" value={data.metrics.near_deadline}/><DashboardMetric label="نتیجه موفق" value={data.metrics.successful_results}/>
    </div>
    <div className="pdp-compact-dashboard-foot"><span>پیگیری عقب‌افتاده: {fa.format(data.management.overdue_actions)}</span><span>بدون مسئول: {fa.format(data.management.without_responsible)}</span><span>ارجاع مستقیم فعال: {fa.format(data.management.direct_active)}</span></div>
  </section>;
}

export default function ProcurementCompactWorkspaceStableEnhancement() {
  const guarded = window as CompactWindow;
  const [noticePayload, setNoticePayload] = useState<NoticePayload | null>(null);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [sourceNames, setSourceNames] = useState<string[]>([]);
  const [filterHost, setFilterHost] = useState<HTMLElement | null>(null);
  const [dashboardHost, setDashboardHost] = useState<HTMLElement | null>(null);
  const [deadlineStatus] = useState(guarded.__pdpCompactDeadlineStatus || "");
  const [publishedOn] = useState(guarded.__pdpCompactPublishedOn || "");
  const [bulkScope, setBulkScope] = useState<"page" | "all">("page");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [, setViewRevision] = useState(0);

  const refreshDashboard = useCallback(() => {
    if (getProcurementStableViewState().top !== "dashboard") return;
    void fetch(COMPACT_DASHBOARD_PATH, { credentials: "include", headers: { Accept: "application/json" }, cache: "no-store" })
      .then(async (response) => { if (!response.ok) throw new Error(`dashboard-${response.status}`); return await response.json() as DashboardPayload; })
      .then(setDashboard).catch(() => undefined);
  }, []);

  useEffect(() => {
    void fetch(`${PROCUREMENT_API}/sources/`, { credentials: "include", headers: { Accept: "application/json" } })
      .then(async (response) => response.ok ? await response.json() as SourcePayload : [])
      .then((payload) => {
        const rows = Array.isArray(payload) ? payload : (payload.results || []);
        setSourceNames(rows.map((row) => normalize(row.name)).filter(Boolean));
      }).catch(() => undefined);
  }, []);

  useEffect(() => {
    let frame = 0;
    const syncDom = () => {
      frame = 0;
      hideLiveDatabaseBanner();
      setFilterHost(ensureFilterHost());
      setDashboardHost(ensureDashboardHost());
      ensureSourceOptions(sourceNames);
      enhanceRecordCards(noticePayload);
    };
    const scheduleSync = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(syncDom);
    };
    const onData = (event: Event) => {
      setNoticePayload((event as CustomEvent<NoticePayload>).detail || null);
      scheduleSync();
    };
    const onState = () => {
      setViewRevision((value) => value + 1);
      setMessage("");
      scheduleSync();
      if (getProcurementStableViewState().top === "dashboard") refreshDashboard();
    };
    const onSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (detail?.source === "compact-workspace") return;
      scheduleSync();
      if (detail?.dashboard || getProcurementStableViewState().top === "dashboard") refreshDashboard();
    };
    window.addEventListener(DATA_EVENT, onData);
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
    scheduleSync();
    refreshDashboard();
    return () => {
      window.removeEventListener(DATA_EVENT, onData);
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, onSync);
      window.cancelAnimationFrame(frame);
    };
  }, [noticePayload, sourceNames, refreshDashboard]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setFilterHost(ensureFilterHost());
      setDashboardHost(ensureDashboardHost());
      enhanceRecordCards(noticePayload);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [noticePayload, dashboard]);

  const bulkDismiss = useCallback(async () => {
    const top = activeTopTab();
    if (top !== "مناقصات" && top !== "استعلامات") return;
    if (activeWorkflow() !== "پیشنهادی" || !noticePayload) return;
    const count = bulkScope === "page" ? noticePayload.results.length : noticePayload.count;
    if (!count) return;
    const scopeText = bulkScope === "page" ? "پیشنهادهای همین صفحه" : "همه پیشنهادهای مطابق فیلتر فعلی";
    if (!window.confirm(`${scopeText} (${fa.format(count)} مورد) از فهرست پیشنهادی حذف شوند؟ خود فراخوان‌ها و سابقه تحلیل حذف نمی‌شوند.`)) return;
    setBulkBusy(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const state = getProcurementStableViewState();
      const params = new URLSearchParams({ notice_type: state.top === "tenders" ? "tender" : "inquiry", workflow: "recommended" });
      if (deadlineStatus) params.set("deadline_status", deadlineStatus);
      if (publishedOn) params.set("published_on", publishedOn);
      const body = bulkScope === "all"
        ? { dismiss_all: true, reason: "حذف گروهی از فهرست پیشنهادی توسط کاربر" }
        : { notice_ids: noticePayload.results.map((item) => item.id), reason: "حذف گروهی از صفحه جاری فهرست پیشنهادی توسط کاربر" };
      const response = await fetch(`${BULK_DISMISS_PATH}?${params.toString()}`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" }, body: JSON.stringify(body),
      });
      const payload = await response.json() as { dismissed?: number; detail?: string };
      if (!response.ok) throw new Error(payload.detail || "حذف گروهی پیشنهادها انجام نشد.");
      setMessage(`${fa.format(payload.dismissed || 0)} پیشنهاد از فهرست پیشنهادی حذف شد؛ فراخوان‌ها و سابقه تحلیل حفظ شدند.`);
      (window as CompactWindow).__pdpStableListCache?.clear();
      emitProcurementUiSync({ source: "compact-workspace", bulkWorkspace: true, dashboard: true });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "حذف گروهی پیشنهادها انجام نشد.");
    } finally {
      setBulkBusy(false);
    }
  }, [bulkScope, noticePayload, deadlineStatus, publishedOn]);

  const top = activeTopTab();
  const showBulk = (top === "مناقصات" || top === "استعلامات") && activeWorkflow() === "پیشنهادی";
  const filterPortal = filterHost ? createPortal(<>
    {showBulk && <div className="pdp-compact-bulk-control"><select value={bulkScope} onChange={(event) => setBulkScope(event.target.value as "page" | "all")}><option value="page">همین صفحه</option><option value="all">همه نتایج فیلترشده</option></select><button type="button" disabled={bulkBusy || !noticePayload?.count} onClick={() => void bulkDismiss()}>{bulkBusy ? "در حال حذف..." : "حذف گروهی پیشنهادها"}</button></div>}
    {message && !showBulk && <small className="pdp-compact-message">{message}</small>}
  </>, filterHost) : null;
  const dashboardPortal = dashboardHost && dashboard ? createPortal(<DashboardBox data={dashboard}/>, dashboardHost) : null;

  return <>
    <style>{`
      .pdp-compact-record{padding:6px 9px!important;gap:6px!important;grid-template-columns:minmax(0,1fr) minmax(145px,.23fr)!important;min-height:0!important}
      .pdp-compact-record h3{font-size:15px!important;line-height:1.5!important;margin:2px 0 1px!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;-webkit-line-clamp:unset!important}
      .pdp-compact-record h3.pdp-full-title-long{display:-webkit-box!important;overflow:hidden!important;-webkit-box-orient:vertical;-webkit-line-clamp:2!important}
      .pdp-compact-record p{font-size:12px!important;line-height:1.45!important;margin:1px 0!important}.pdp-compact-record>div:last-child{gap:4px!important;padding-inline-start:7px!important}
      .pdp-compact-badge-group{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin:3px 0}.pdp-compact-source,.pdp-compact-chip{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border-radius:999px;border:1px solid #cbd5e1;background:#f8fafc;color:#334155;font-size:10.5px;font-weight:700;text-decoration:none;white-space:nowrap}.pdp-source-0{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.pdp-source-1{border-color:#bfdbfe;background:#eff6ff;color:#1d4ed8}.pdp-source-2{border-color:#fde68a;background:#fffbeb;color:#a16207}.pdp-source-count{background:#f1f5f9}.pdp-deadline-date{background:#fff7ed;border-color:#fed7aa;color:#9a3412}
      .pdp-compact-dismiss{width:auto!important;min-height:28px!important;padding:4px 7px!important;font-size:10.5px!important}.pdp-compact-filter-label{display:grid;gap:3px;font-size:11px}.pdp-compact-filter-label select,.pdp-compact-filter-label input{width:100%;min-height:34px;border:1px solid rgba(15,23,42,.16);border-radius:8px;padding:5px 7px;background:white;font:inherit}.pdp-compact-bulk-control{display:flex;align-items:end;gap:5px}.pdp-compact-bulk-control select,.pdp-compact-bulk-control button{min-height:34px;border:1px solid #cbd5e1;border-radius:8px;background:white;padding:5px 7px;font:inherit;font-size:11px}.pdp-compact-bulk-control button{border-color:#fecaca;background:#fff1f2;color:#be123c;font-weight:700}.pdp-compact-message{align-self:end;color:#0f766e;font-weight:700;grid-column:1/-1}
      .pdp-compact-dashboard-box{background:white;border:1px solid #dbe3ec;border-radius:14px;padding:12px;margin-bottom:12px;box-shadow:0 4px 14px rgba(15,23,42,.04)}.pdp-compact-dashboard-heading{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px;flex-wrap:wrap}.pdp-compact-dashboard-heading h2{font-size:17px;margin:0 0 2px}.pdp-compact-dashboard-heading small{color:#64748b;font-size:10.5px}.pdp-compact-dashboard-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.pdp-compact-metric{border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:8px 9px;min-height:74px}.pdp-compact-metric>span{display:block;color:#64748b;font-size:10.5px}.pdp-compact-metric>b{display:block;font-size:20px;line-height:1.25;margin:3px 0}.pdp-compact-metric small{display:flex;gap:4px;flex-wrap:wrap}.pdp-compact-metric em{font-style:normal;font-size:9.5px;background:white;border:1px solid #e2e8f0;border-radius:999px;padding:1px 5px}.pdp-compact-dashboard-foot{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;color:#475569;font-size:10.5px}.pdp-compact-dashboard-foot span{background:#f8fafc;border-radius:999px;padding:3px 7px}
      @media(max-width:900px){.pdp-compact-dashboard-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.pdp-compact-record{grid-template-columns:1fr!important}}
    `}</style>
    {filterPortal}{dashboardPortal}
  </>;
}
