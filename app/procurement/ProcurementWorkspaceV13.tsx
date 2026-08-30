"use client";

import Link from "next/link";
import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import ConnectorHealthBanner from "./ConnectorHealthBanner";
import {
  ProcurementV9NativeFilters,
  ProcurementV9NativeToolbar,
  resetProcurementV9NativeFilters,
} from "./ProcurementWebPreviewV9Enhancement";
import { procurementDataClient, type ProcurementQueryContext } from "./procurementDataClient";
import { getProcurementV9FilterState } from "./procurementV9FilterState";
import { setProcurementStableViewState } from "./procurementStableViewState";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";
import styles from "./workspace-v4.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "reports" | "prompts" | "keywords" | "company" | "versions";
type Importance = "low" | "medium" | "high" | "very_high";
type UrgencyTone = "critical" | "high" | "medium" | "normal" | "unknown";
type DataMode = "loading" | "live" | "unauthorized" | "error";
type PageSize = 30 | 50 | 100;

type ApiNotice = {
  id: string;
  reference_code: string | null;
  resolved_notice_type: "tender" | "inquiry";
  notice_type_label: string;
  title: string;
  employer_name: string;
  province: string;
  published_date: string | null;
  submission_deadline: string | null;
  processing_status: string;
  processing_status_label: string;
  importance: Importance;
  importance_label: string;
  is_recommended: boolean;
  case_stage: string | null;
  case_stage_label: string | null;
  case_responsible_username?: string;
  submission_document_count?: number;
  source_name: string;
  source_url: string;
  detail_url: string;
  first_seen_at: string;
  last_seen_at: string;
};

type ApiDirectOpportunity = {
  id: string;
  reference_code: string | null;
  title: string;
  employer_name: string;
  opportunity_type: string;
  opportunity_type_label: string;
  business_opportunity_type?: string;
  business_opportunity_type_label?: string;
  activity_domain?: string;
  activity_domain_label?: string;
  stage: string;
  stage_label: string;
  responsible_username: string;
  next_action_due: string | null;
  domain: string;
  province: string;
  probability_percent: number | null;
  importance: Importance;
  importance_label: string;
  last_activity_at: string;
};

type ApiConnector = {
  id: string;
  source: string;
  key: string;
  notice_type: "tender" | "inquiry";
  notice_type_label: string;
  enabled: boolean;
  status: string;
  status_label: string;
};

type ApiSource = {
  id: string;
  name: string;
  enabled: boolean;
  status?: string;
  connectors: ApiConnector[];
};

type ApiExtractionRun = {
  id: string;
  mode: "incremental" | "manual_range";
  mode_label: string;
  status: string;
  status_label: string;
  connectors: ApiConnector[];
  pages_processed: number;
  records_seen: number;
  records_new: number;
  records_updated: number;
  records_duplicate: number;
  records_failed: number;
  summary: { connectors?: Record<string, Record<string, unknown>> };
  created_at: string;
  finished_at: string | null;
};

type ApiAutomationSettings = {
  id: string;
  enabled: boolean;
  cadence: "daily" | "hourly";
  interval_minutes: number;
  daily_time: string | null;
  timezone_name: string;
  analysis_delay_minutes: number;
  scheduled_task_enabled: boolean;
  next_extraction_at: string | null;
};

type MetricCounts = { total?: number; tender?: number; inquiry?: number };
type DashboardCase = { id: string; title: string; subtitle: string; stage: string; deadline: string | null; kind: "notice" | "direct" };
type DashboardPayload = {
  generated_at?: string;
  metrics?: {
    all_notices?: MetricCounts;
    new_today?: MetricCounts;
    analysis_remaining?: MetricCounts;
    recommended?: MetricCounts;
    selected?: MetricCounts;
    submitted?: MetricCounts;
    near_deadline?: MetricCounts;
    successful_results?: MetricCounts;
    unsuccessful_results?: MetricCounts;
  };
  management?: { overdue_actions?: number; without_responsible?: number; direct_active?: number; direct_total?: number };
  active_cases?: DashboardCase[];
};

type CollectionPayload<T> = T[] | { count?: number; results?: T[]; next?: string | null; page?: number; page_size?: number };

type ScheduleState = {
  enabled: boolean;
  cadence: "daily" | "hourly";
  dailyTime: string;
  intervalHours: number;
  lookbackDays: number;
};

type DetailItem = { kind: "notice"; item: ApiNotice } | { kind: "direct"; item: ApiDirectOpportunity } | null;
type DirectCacheEntry = { payload: { count: number; results: ApiDirectOpportunity[] }; fetchedAt: number };
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const fa = new Intl.NumberFormat("fa-IR");
const dateFa = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" });
const dateTimeFa = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

const tabs: [Tab, string][] = [
  ["dashboard", "داشبورد مدیریتی"],
  ["tenders", "مناقصات"],
  ["inquiries", "استعلامات"],
  ["direct", "ارجاعات مستقیم"],
  ["management", "مدیریت زیرسامانه"],
];
const standardViews: [WorkflowView, string][] = [
  ["recommended", "پیشنهادی"],
  ["selected", "منتخب"],
  ["submitted", "ارسال‌شده"],
  ["results", "نتایج"],
];
const managementTabs: [ManagementView, string][] = [
  ["extraction", "استخراج و منابع"],
  ["reports", "گزارش استخراج"],
  ["prompts", "نقش و Prompt"],
  ["keywords", "کلیدواژه‌ها"],
  ["company", "پروفایل، صلاحیت و رزومه"],
  ["versions", "نسخه‌ها و فعال‌سازی"],
];
const importanceLabels: Record<Importance, string> = { low: "کم", medium: "متوسط", high: "زیاد", very_high: "بسیار زیاد" };
const importanceStyles: Record<Importance, CSSProperties> = {
  low: { background: "#f1f5f9", color: "#475569", borderColor: "#cbd5e1" },
  medium: { background: "#eff6ff", color: "#1d4ed8", borderColor: "#bfdbfe" },
  high: { background: "#fff7ed", color: "#c2410c", borderColor: "#fed7aa" },
  very_high: { background: "#fef2f2", color: "#b91c1c", borderColor: "#fecaca" },
};

const selectedNoticeStages = new Set(["selected", "evaluating", "participate", "preparing", "ready_to_submit"]);
const submittedNoticeStages = new Set(["submitted", "awaiting_result"]);
const resultNoticeStages = new Set(["won", "lost", "cancelled", "renewed", "do_not_participate"]);
const recommendedDirectStages = new Set(["new", "reviewing", "following_up", "negotiating"]);
const selectedDirectStages = new Set(["selected", "preparing"]);
const resultDirectStages = new Set(["won", "lost", "stopped", "deferred", "converted_to_notice", "converted_to_contract"]);

const filterStyle = { display:"grid", gridTemplateColumns:"minmax(220px,2fr) repeat(auto-fit,minmax(115px,1fr))", gap:7, padding:9, border:"1px solid rgba(15,23,42,.12)", borderRadius:12, background:"#f8fafc", marginBottom:10 } as const;
const inputStyle = { width:"100%", minHeight:34, border:"1px solid rgba(15,23,42,.16)", borderRadius:8, padding:"6px 8px", background:"white" } as const;
const sourceBadgeStyle = { display:"inline-flex", alignItems:"center", minHeight:19, padding:"1px 6px", borderRadius:999, border:"1px solid rgba(15,118,110,.22)", background:"#ecfdf5", color:"#0f766e", fontSize:10, fontWeight:700, textDecoration:"none", whiteSpace:"nowrap" } as const;
const compactViewStyle = { minHeight:24, padding:"3px 8px", borderRadius:7, fontSize:11 } as const;
const compactRecordStyle = { padding:"9px 11px", gap:9, gridTemplateColumns:"minmax(0,1fr) minmax(185px,.32fr)" } as const;
const compactDecisionStyle = { gap:5, paddingInlineStart:10 } as const;
const importanceBadgeBase = { display:"inline-flex", alignItems:"center", minHeight:22, padding:"3px 8px", borderRadius:999, border:"1px solid", fontSize:11, fontWeight:700, whiteSpace:"nowrap" } as const;

function formatDate(value: string | null | undefined) {
  if (!value) return "نامشخص";
  const normalized = value.length === 10 ? `${value}T12:00:00` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : dateFa.format(date);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFa.format(date);
}

function urgency(value: string | null) {
  if (!value) return { tone:"unknown" as UrgencyTone, label:"تاریخ نامشخص", remaining:"نامشخص" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone:"critical" as UrgencyTone, label:"مهلت گذشته", remaining:`${fa.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone:"critical" as UrgencyTone, label:"فوریت بحرانی", remaining:`${fa.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone:"high" as UrgencyTone, label:"فوریت زیاد", remaining:`${fa.format(Math.ceil(hours/24))} روز باقی‌مانده` };
  if (hours <= 168) return { tone:"medium" as UrgencyTone, label:"فوریت متوسط", remaining:`${fa.format(Math.ceil(hours/24))} روز باقی‌مانده` };
  return { tone:"normal" as UrgencyTone, label:"عادی", remaining:`${fa.format(Math.ceil(hours/24))} روز باقی‌مانده` };
}

function allLabel(tab: Tab) {
  if (tab === "tenders") return "مناقصات اخیر";
  if (tab === "inquiries") return "استعلامات اخیر";
  return "ارجاعات مستقیم اخیر";
}

function workflowCode(view: WorkflowView) {
  return view === "all" ? "recent" : view;
}

function directWorkflowCode(view: WorkflowView) {
  return view === "all" ? "recommended" : view;
}

function sameOriginPath(value: string) {
  const url = new URL(value, window.location.origin);
  return `${url.pathname}${url.search}`;
}

async function fetchCollection<T>(path: string, maxPages = 2): Promise<T[]> {
  const items: T[] = [];
  let next: string | null = path;
  let pages = 0;
  while (next && pages < maxPages) {
    const response = await fetch(next, { credentials: "include", headers: { Accept: "application/json" } });
    if (response.status === 401 || response.status === 403) throw new Error("unauthorized");
    if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) throw new Error(`api-${response.status}`);
    const payload = await response.json() as CollectionPayload<T>;
    if (Array.isArray(payload)) {
      items.push(...payload);
      next = null;
    } else {
      items.push(...(payload.results || []));
      next = payload.next ? sameOriginPath(payload.next) : null;
    }
    pages += 1;
  }
  return items;
}

async function fetchRecord<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "include", headers: { Accept: "application/json" } });
  if (response.status === 401 || response.status === 403) throw new Error("unauthorized");
  if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) throw new Error(`api-${response.status}`);
  return response.json() as Promise<T>;
}

async function fetchAutomationSettings(): Promise<ApiAutomationSettings | null> {
  try {
    return await fetchRecord<ApiAutomationSettings>(`${PROCUREMENT_API}/automation-settings/default/`);
  } catch (error) {
    if (!(error instanceof Error) || error.message !== "api-404") throw error;
    const items = await fetchCollection<ApiAutomationSettings>(`${PROCUREMENT_API}/automation-settings/`);
    return items[0] || null;
  }
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("session-unavailable");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function connectorSummaryNumber(run: ApiExtractionRun, connector: ApiConnector, key: string, fallback: number) {
  const value = run.summary?.connectors?.[connector.key]?.[key];
  return typeof value === "number" ? value : fallback;
}

function scheduleFromAutomation(current: ScheduleState, settings: ApiAutomationSettings): ScheduleState {
  return {
    ...current,
    enabled: settings.enabled,
    cadence: settings.cadence,
    dailyTime: settings.daily_time?.slice(0, 5) || "11:00",
    intervalHours: Math.max(1, Math.round(settings.interval_minutes / 60)),
  };
}

function advancedFilters() {
  const filters = getProcurementV9FilterState();
  return {
    sources: filters.sources,
    provinces: filters.provinces,
    importance: filters.importance,
    urgency: filters.urgency,
    deadlineStatuses: filters.deadlineStatuses,
    publishedFrom: filters.publishedFrom,
    publishedTo: filters.publishedTo,
    opportunityTypes: filters.opportunityTypes,
    activityDomains: filters.activityDomains,
  };
}

function appendRepeated(params: URLSearchParams, key: string, values: string[]) {
  values.forEach((value) => params.append(key, value));
}

function PaginationControls({ page, pageSize, count, loading, onPage, onPageSize }: {
  page: number; pageSize: PageSize; count: number; loading: boolean;
  onPage: (page: number) => void; onPageSize: (size: PageSize) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,flexWrap:"wrap",marginTop:10,padding:"8px 10px",border:"1px solid #e2e8f0",borderRadius:10,background:"#f8fafc"}}>
    <span>{loading ? "در حال به‌روزرسانی..." : `${fa.format(count)} رکورد · صفحه ${fa.format(page)} از ${fa.format(pages)}`}</span>
    <div style={{display:"flex",alignItems:"center",gap:7}}>
      <label style={{display:"flex",alignItems:"center",gap:5}}>تعداد<select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value) as PageSize)}><option value={30}>۳۰</option><option value={50}>۵۰</option><option value={100}>۱۰۰</option></select></label>
      <button type="button" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>صفحه قبل</button>
      <button type="button" disabled={loading || page >= pages} onClick={() => onPage(page + 1)}>صفحه بعد</button>
    </div>
  </div>;
}

export default function ProcurementWorkspaceV13() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [provinceFilter, setProvinceFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [urgencyFilter, setUrgencyFilter] = useState("");
  const [directTypeFilter, setDirectTypeFilter] = useState("");
  const [mode, setMode] = useState<DataMode>("loading");
  const [username, setUsername] = useState("");
  const [notices, setNotices] = useState<ApiNotice[]>([]);
  const [noticeCount, setNoticeCount] = useState(0);
  const [noticePage, setNoticePage] = useState(1);
  const [noticePageSize, setNoticePageSize] = useState<PageSize>(50);
  const [noticeLoading, setNoticeLoading] = useState(false);
  const [noticeError, setNoticeError] = useState("");
  const [directReferrals, setDirectReferrals] = useState<ApiDirectOpportunity[]>([]);
  const [directCount, setDirectCount] = useState(0);
  const [directPage, setDirectPage] = useState(1);
  const [directPageSize, setDirectPageSize] = useState<PageSize>(50);
  const [directLoading, setDirectLoading] = useState(false);
  const [directError, setDirectError] = useState("");
  const [dashboard, setDashboard] = useState<DashboardPayload>({});
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [extractionRuns, setExtractionRuns] = useState<ApiExtractionRun[]>([]);
  const [automation, setAutomation] = useState<ApiAutomationSettings | null>(null);
  const [schedule, setSchedule] = useState<ScheduleState>({ enabled:false, cadence:"daily", dailyTime:"11:00", intervalHours:1, lookbackDays:7 });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [selectingNoticeIds, setSelectingNoticeIds] = useState<Set<string>>(() => new Set());
  const [refresh, setRefresh] = useState(0);
  const [viewRefresh, setViewRefresh] = useState(0);
  const [dashboardRefresh, setDashboardRefresh] = useState(0);
  const [directRefresh, setDirectRefresh] = useState(0);
  const [detail, setDetail] = useState<DetailItem>(null);
  const [directModal, setDirectModal] = useState(false);
  const [updatingConnector, setUpdatingConnector] = useState("");
  const hasLoadedOnce = useRef(false);
  const managementLoadVersion = useRef(-1);
  const directController = useRef<AbortController | null>(null);
  const directGeneration = useRef(0);
  const directCache = useRef(new Map<string, DirectCacheEntry>());

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const workflow = tab === "tenders" || tab === "inquiries" ? noticeView : tab === "direct" ? directView : "all";
    setProcurementStableViewState({ top: tab, workflow });
  }, [tab, noticeView, directView]);

  useEffect(() => {
    setNoticePage(1);
    setDirectPage(1);
  }, [debouncedSearch, sourceFilter, provinceFilter, importanceFilter, urgencyFilter, directTypeFilter, viewRefresh]);

  useEffect(() => {
    let active = true;
    async function authenticate() {
      if (!hasLoadedOnce.current) setMode("loading");
      try {
        const sessionResponse = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
        if (!sessionResponse.ok) throw new Error("session-unavailable");
        const session = await sessionResponse.json() as { authenticated?: boolean; username?: string | null };
        if (!active) return;
        if (!session.authenticated) {
          setUsername("");
          setMode("unauthorized");
          return;
        }
        setUsername(session.username || "");
        hasLoadedOnce.current = true;
        setMode("live");
      } catch {
        if (!active) return;
        if (!hasLoadedOnce.current) setMode("error");
        else setMessage("به‌روزرسانی نشست موقتاً انجام نشد؛ داده‌های قبلی حفظ شدند.");
      }
    }
    void authenticate();
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    if (mode !== "live" || tab !== "dashboard") return;
    const controller = new AbortController();
    let active = true;
    setDashboardLoading(true);
    void fetch(`${PROCUREMENT_API}/ui/dashboard/`, {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`dashboard-${response.status}`);
      const payload = await response.json() as DashboardPayload;
      if (active) setDashboard(payload);
    }).catch((error) => {
      if (active && !(error instanceof DOMException && error.name === "AbortError")) {
        setMessage("به‌روزرسانی داشبورد موقتاً انجام نشد؛ آخرین داده سالم حفظ شد.");
      }
    }).finally(() => { if (active) setDashboardLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [mode, tab, dashboardRefresh]);

  useEffect(() => {
    if (mode !== "live" || (tab !== "tenders" && tab !== "inquiries")) return;
    const extra = advancedFilters();
    const context: ProcurementQueryContext = {
      noticeType: tab === "tenders" ? "tender" : "inquiry",
      workflow: workflowCode(noticeView),
      page: noticePage,
      pageSize: noticePageSize,
      sort: "-publication_sort,-last_seen_at,-id",
      filters: {
        search: debouncedSearch,
        source_name: extra.sources.length ? extra.sources : (sourceFilter ? [sourceFilter] : []),
        province: extra.provinces.length ? extra.provinces : (provinceFilter ? [provinceFilter] : []),
        importance: extra.importance.length ? extra.importance : (importanceFilter ? [importanceFilter] : []),
        urgency: extra.urgency.length ? extra.urgency : (urgencyFilter ? [urgencyFilter] : []),
        deadline_status: extra.deadlineStatuses,
        published_from: extra.publishedFrom,
        published_to: extra.publishedTo,
        business_opportunity_type: extra.opportunityTypes,
        activity_domain: extra.activityDomains,
      },
    };
    let active = true;
    setNoticeLoading(true);
    setNoticeError("");
    procurementDataClient.abortAllExcept(context);
    void procurementDataClient.staleWhileRevalidate<ApiNotice>(context, (fresh) => {
      if (!active) return;
      setNotices(fresh.payload.results || []);
      setNoticeCount(Number(fresh.payload.count || fresh.payload.results?.length || 0));
    }).then((result) => {
      if (!active) return;
      setNotices(result.payload.results || []);
      setNoticeCount(Number(result.payload.count || result.payload.results?.length || 0));
    }).catch((error) => {
      if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
      setNoticeError("دریافت این فهرست موقتاً ناموفق بود؛ داده سالم قبلی حفظ شده است.");
    }).finally(() => { if (active) setNoticeLoading(false); });
    return () => { active = false; procurementDataClient.abort(context); };
  }, [mode, tab, noticeView, noticePage, noticePageSize, debouncedSearch, sourceFilter, provinceFilter, importanceFilter, urgencyFilter, viewRefresh]);

  useEffect(() => {
    if (mode !== "live" || tab !== "direct") return;
    const extra = advancedFilters();
    const params = new URLSearchParams();
    params.set("page", String(directPage));
    params.set("page_size", String(directPageSize));
    params.set("ordering", "-last_activity_at,-id");
    params.set("workflow_view", directWorkflowCode(directView));
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (directTypeFilter) params.set("opportunity_type", directTypeFilter);
    appendRepeated(params, "province", extra.provinces.length ? extra.provinces : (provinceFilter ? [provinceFilter] : []));
    appendRepeated(params, "importance", extra.importance.length ? extra.importance : (importanceFilter ? [importanceFilter] : []));
    appendRepeated(params, "urgency", extra.urgency.length ? extra.urgency : (urgencyFilter ? [urgencyFilter] : []));
    appendRepeated(params, "business_opportunity_type", extra.opportunityTypes);
    appendRepeated(params, "activity_domain", extra.activityDomains);
    const url = `${PROCUREMENT_API}/direct-opportunities/?${params.toString()}`;
    const cacheKey = url;
    const cached = directCache.current.get(cacheKey);
    if (cached) {
      setDirectReferrals(cached.payload.results);
      setDirectCount(cached.payload.count);
    }
    directController.current?.abort();
    const controller = new AbortController();
    directController.current = controller;
    const generation = directGeneration.current + 1;
    directGeneration.current = generation;
    setDirectLoading(true);
    setDirectError("");
    void fetch(url, { credentials: "include", headers: { Accept: "application/json" }, signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`direct-${response.status}`);
      const payload = await response.json() as CollectionPayload<ApiDirectOpportunity>;
      const results = Array.isArray(payload) ? payload : (payload.results || []);
      const count = Array.isArray(payload) ? results.length : Number(payload.count || results.length);
      if (directGeneration.current !== generation) throw new DOMException("Stale direct response discarded", "AbortError");
      directCache.current.set(cacheKey, { payload: { count, results }, fetchedAt: Date.now() });
      setDirectReferrals(results);
      setDirectCount(count);
    }).catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setDirectError("دریافت ارجاعات مستقیم موقتاً ناموفق بود؛ داده سالم قبلی حفظ شده است.");
    }).finally(() => {
      if (directGeneration.current === generation) setDirectLoading(false);
    });
    return () => controller.abort();
  }, [mode, tab, directView, directPage, directPageSize, debouncedSearch, provinceFilter, importanceFilter, urgencyFilter, directTypeFilter, directRefresh, viewRefresh]);

  useEffect(() => {
    const updateManagement = () => {
      if (tab !== "management") return;
      managementLoadVersion.current = -1;
      setRefresh((value) => value + 1);
    };
    const handleSync = (event: Event) => {
      const sync = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!sync) return;
      if (sync.bulkWorkspace) {
        procurementDataClient.invalidate();
        directCache.current.clear();
        setViewRefresh((value) => value + 1);
      }
      if (sync.noticeId && sync.source !== "workspace-v13") {
        procurementDataClient.invalidate();
        setViewRefresh((value) => value + 1);
      }
      if (sync.directId && sync.source !== "workspace-v13") {
        directCache.current.clear();
        setDirectRefresh((value) => value + 1);
      }
      if (sync.dashboard) setDashboardRefresh((value) => value + 1);
      if (sync.management) updateManagement();
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
  }, [tab]);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    let lastRevision: number | null = null;
    const checkRevision = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const response = await fetch(`${PROCUREMENT_API}/interaction/revision/`, { credentials: "include", headers: { Accept: "application/json" } });
        if (!response.ok) return;
        const payload = await response.json() as { revision?: number };
        const revision = Number(payload.revision || 0);
        if (cancelled) return;
        if (lastRevision !== null && revision > lastRevision) {
          procurementDataClient.invalidate();
          directCache.current.clear();
          setViewRefresh((value) => value + 1);
          setDirectRefresh((value) => value + 1);
          setDashboardRefresh((value) => value + 1);
        }
        lastRevision = revision;
      } catch {
      }
    };
    void checkRevision();
    const timer = window.setInterval(checkRevision, 30000);
    const onFocus = () => { void checkRevision(); };
    window.addEventListener("focus", onFocus);
    return () => { cancelled = true; window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [mode]);

  useEffect(() => {
    if (tab !== "management" || mode !== "live" || managementLoadVersion.current === refresh) return;
    managementLoadVersion.current = refresh;
    let active = true;

    async function loadManagementData() {
      const [sourceResult, runResult, automationResult] = await Promise.allSettled([
        fetchCollection<ApiSource>(`${PROCUREMENT_API}/sources/`, 1),
        fetchCollection<ApiExtractionRun>(`${PROCUREMENT_API}/extraction-runs/?ordering=-created_at&page_size=20`, 1),
        fetchAutomationSettings(),
      ]);
      if (!active) return;

      let failures = 0;
      if (sourceResult.status === "fulfilled") setSources(sourceResult.value); else failures += 1;
      if (runResult.status === "fulfilled") setExtractionRuns(runResult.value); else failures += 1;
      if (automationResult.status === "fulfilled") {
        const currentAutomation = automationResult.value;
        setAutomation(currentAutomation);
        if (currentAutomation) setSchedule((current) => scheduleFromAutomation(current, currentAutomation));
      } else failures += 1;

      if (failures) {
        managementLoadVersion.current = -1;
        setMessage(failures === 3
          ? "اطلاعات مدیریت زیرسامانه موقتاً بارگذاری نشد؛ سایر بخش‌ها فعال‌اند."
          : "بخشی از اطلاعات مدیریت زیرسامانه موقتاً بارگذاری نشد؛ بخش‌های سالم همچنان قابل استفاده‌اند.");
      }
    }

    void loadManagementData();
    return () => { active = false; };
  }, [tab, mode, refresh]);

  const activeRun = extractionRuns.find((run) => run.status === "queued" || run.status === "running");
  useEffect(() => {
    if (!activeRun) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(`${PROCUREMENT_API}/extraction-runs/${activeRun.id}/`, { credentials: "include", headers: { Accept: "application/json" } });
        if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return;
        const updated = await response.json() as ApiExtractionRun;
        if (cancelled) return;
        setExtractionRuns((current) => current.map((run) => run.id === updated.id ? updated : run));
        if (updated.status !== "queued" && updated.status !== "running") {
          window.clearInterval(timer);
          emitProcurementUiSync({ source:"workspace-v13", dashboard:true, management:true });
        }
      } catch {
      }
    };
    const timer = window.setInterval(poll, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeRun?.id]);

  const noticeViews: [WorkflowView, string][] = [["all", allLabel(tab)], ...standardViews];
  const directViews: [WorkflowView, string][] = [["all", allLabel("direct")], ...standardViews.filter(([view]) => view !== "recommended")];
  const filteredNotices = notices;
  const filteredDirect = directReferrals;
  const metric = (key: keyof NonNullable<DashboardPayload["metrics"]>) => Number(dashboard.metrics?.[key]?.total || 0);
  const dashboardSelected = metric("selected");
  const dashboardSubmitted = metric("submitted");
  const recommendedCount = tab === "dashboard" ? metric("recommended") : notices.filter((item) => item.is_recommended && !item.case_stage).length + directReferrals.filter((item) => recommendedDirectStages.has(item.stage)).length;
  const selectedCount = tab === "dashboard" ? dashboardSelected : notices.filter((item) => selectedNoticeStages.has(item.case_stage || "")).length + directReferrals.filter((item) => selectedDirectStages.has(item.stage)).length;
  const submittedCount = tab === "dashboard" ? dashboardSubmitted : notices.filter((item) => submittedNoticeStages.has(item.case_stage || "")).length + directReferrals.filter((item) => item.stage === "submitted").length;
  const urgentCount = tab === "dashboard" ? metric("near_deadline") : notices.filter((item) => ["critical", "high"].includes(urgency(item.submission_deadline).tone) && !resultNoticeStages.has(item.case_stage || "")).length;
  const wonCount = tab === "dashboard" ? metric("successful_results") : notices.filter((item) => item.case_stage === "won").length + directReferrals.filter((item) => item.stage === "won" || item.stage === "converted_to_contract").length;
  const lostCount = tab === "dashboard" ? metric("unsuccessful_results") : notices.filter((item) => item.case_stage === "lost").length + directReferrals.filter((item) => item.stage === "lost").length;
  const winRate = wonCount + lostCount ? Math.round((wonCount / (wonCount + lostCount)) * 100) : 0;
  const activeCases = tab === "dashboard" ? (dashboard.active_cases || []) : [
    ...notices.filter((item) => selectedNoticeStages.has(item.case_stage || "") || submittedNoticeStages.has(item.case_stage || "")).map((item) => ({ id:item.id, title:item.title, subtitle:`${item.notice_type_label} · ${item.employer_name || "کارفرما نامشخص"}`, stage:item.case_stage_label || "منتخب", deadline:item.submission_deadline, kind:"notice" as const })),
    ...directReferrals.filter((item) => selectedDirectStages.has(item.stage) || item.stage === "submitted").map((item) => ({ id:item.id, title:item.title, subtitle:`ارجاع مستقیم · ${item.employer_name || "کارفرما نامشخص"}`, stage:item.stage_label, deadline:item.next_action_due, kind:"direct" as const })),
  ].slice(0, 20);

  const enabledConnectors = sources.flatMap((source) => source.connectors).filter((connector) => connector.enabled && connector.status !== "pending_source_analysis");
  const sourceById = new Map(sources.map((source) => [source.id, source.name]));
  const extractionRows = extractionRuns.flatMap((run) => run.connectors.length ? run.connectors.map((connector) => ({
    key: `${run.id}-${connector.id}`,
    time: formatDateTime(run.finished_at || run.created_at),
    source: sourceById.get(connector.source) || connector.key,
    type: connector.notice_type_label,
    pages: connectorSummaryNumber(run, connector, "pages", run.pages_processed),
    records: connectorSummaryNumber(run, connector, "seen", run.records_seen),
    fresh: connectorSummaryNumber(run, connector, "new", run.records_new),
    updated: connectorSummaryNumber(run, connector, "updated", run.records_updated),
    duplicate: connectorSummaryNumber(run, connector, "duplicate", run.records_duplicate),
    status: String(run.summary?.connectors?.[connector.key]?.status || run.status_label),
  })) : [{ key:run.id, time:formatDateTime(run.finished_at || run.created_at), source:"—", type:run.mode_label, pages:run.pages_processed, records:run.records_seen, fresh:run.records_new, updated:run.records_updated, duplicate:run.records_duplicate, status:run.status_label }]).slice(0, 60);

  function resetFilters() {
    setSearch(""); setSourceFilter(""); setProvinceFilter(""); setImportanceFilter(""); setUrgencyFilter(""); setDirectTypeFilter("");
    setNoticePage(1); setDirectPage(1);
  }

  function clearVisibleFilters() {
    resetFilters();
    resetProcurementV9NativeFilters();
    procurementDataClient.invalidate();
    directCache.current.clear();
    setViewRefresh((value) => value + 1);
  }

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 5000);
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("login");
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/auth/login/`, { method:"POST", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify({username:form.get("username"),password:form.get("password")}) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "ورود انجام نشد.");
      notify(`ورود ${payload.username} موفق بود.`);
      setRefresh((value) => value + 1);
    } catch (error) { notify(error instanceof Error ? error.message : "ورود انجام نشد."); } finally { setBusy(""); }
  }

  async function toggleConnector(sourceId: string, connector: ApiConnector) {
    setUpdatingConnector(connector.id);
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/connectors/${connector.id}/`, { method:"PATCH", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify({enabled:!connector.enabled}) });
      const payload = await response.json() as ApiConnector & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "تغییر وضعیت Connector انجام نشد.");
      setSources((current) => current.map((source) => source.id !== sourceId ? source : { ...source, enabled:payload.enabled ? true : source.enabled, connectors:source.connectors.map((candidate) => candidate.id === payload.id ? payload : candidate) }));
      notify(`${connector.notice_type_label} ${sourceById.get(sourceId) || "منبع"} ${payload.enabled ? "فعال" : "غیرفعال"} شد.`);
      emitProcurementUiSync({ source:"workspace-v13", dashboard:true });
    } catch (error) { notify(error instanceof Error ? error.message : "تغییر وضعیت Connector انجام نشد."); } finally { setUpdatingConnector(""); }
  }

  async function runExtraction(modeValue: "incremental" | "manual_range") {
    if (!enabledConnectors.length) { notify("هیچ Connector فعالی برای استخراج وجود ندارد."); return; }
    setBusy(`extract-${modeValue}`);
    try {
      const token = await csrfToken();
      const body: Record<string, unknown> = { connector_ids:enabledConnectors.map((connector) => connector.id), mode:modeValue, include_details:true, analyze_after_success:false };
      if (modeValue === "manual_range") body.lookback_days = schedule.lookbackDays;
      const response = await fetch(`${PROCUREMENT_API}/extraction-runs/`, { method:"POST", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify(body) });
      const payload = await response.json() as ApiExtractionRun & { detail?: string };
      if (response.status === 401 || response.status === 403) throw new Error("برای اجرای استخراج باید با حساب مدیر وارد شوید.");
      if (!response.ok) throw new Error(payload.detail || "درخواست استخراج ثبت نشد.");
      setExtractionRuns((current) => [payload, ...current.filter((item) => item.id !== payload.id)]);
      notify(modeValue === "incremental" ? "استخراج افزایشی واقعی در صف اجرا قرار گرفت." : `استخراج واقعی ${fa.format(schedule.lookbackDays)} روز گذشته در صف قرار گرفت.`);
      setManagementView("reports");
    } catch (error) { notify(error instanceof Error ? error.message : "درخواست استخراج ثبت نشد."); } finally { setBusy(""); }
  }

  async function saveAutomation() {
    if (schedule.cadence === "daily" && !schedule.dailyTime) { notify("برای برنامه روزانه، ساعت استخراج را تعیین کنید."); return; }
    const intervalHours = Number.isFinite(schedule.intervalHours) ? Math.min(168, Math.max(1, Math.round(schedule.intervalHours))) : 1;
    setBusy("automation");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/automation-settings/default/`, { method:"PATCH", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify({ enabled:schedule.enabled, cadence:schedule.cadence, interval_minutes:intervalHours * 60, daily_time:schedule.cadence === "daily" ? schedule.dailyTime : null }) });
      const payload = await response.json() as Partial<ApiAutomationSettings> & { detail?: string } & Record<string, unknown>;
      if (response.status === 401 || response.status === 403) throw new Error("فقط مدیر سیستم اجازه تغییر زمان‌بندی را دارد.");
      if (!response.ok) throw new Error(payload.detail || Object.values(payload).flat().join(" ") || "ذخیره تنظیمات انجام نشد.");
      const saved = payload as ApiAutomationSettings;
      setAutomation(saved); setSchedule((current) => scheduleFromAutomation(current, saved));
      notify("زمان‌بندی استخراج ذخیره شد. ذخیره تنظیمات، استخراج فوری اجرا نمی‌کند.");
      emitProcurementUiSync({ source:"workspace-v13", management:true });
    } catch (error) { notify(error instanceof Error ? error.message : "ذخیره تنظیمات انجام نشد."); } finally { setBusy(""); }
  }

  async function selectNotice(item: ApiNotice) {
    if (selectingNoticeIds.has(item.id) || item.case_stage) return;
    const previous = item;
    setSelectingNoticeIds((current) => new Set(current).add(item.id));
    setNotices((current) => current.map((candidate) => candidate.id === item.id ? { ...candidate, case_stage:"selected", case_stage_label:"منتخب" } : candidate));
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/cases/`, { method:"POST", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify({notice:item.id,stage:"selected"}) });
      const payload = await response.json() as { stage?: string; stage_label?: string; detail?: string; [key: string]: unknown };
      if (!response.ok) throw new Error(payload.detail || Object.values(payload).flat().join(" ") || "انتخاب پرونده انجام نشد.");
      notify("فراخوان به پرونده‌های منتخب اضافه شد.");
      procurementDataClient.invalidate();
      setViewRefresh((value) => value + 1);
      setDashboardRefresh((value) => value + 1);
    } catch (error) {
      setNotices((current) => current.map((candidate) => candidate.id === previous.id ? previous : candidate));
      notify(error instanceof Error ? error.message : "انتخاب پرونده انجام نشد.");
    } finally {
      setSelectingNoticeIds((current) => { const next = new Set(current); next.delete(item.id); return next; });
    }
  }

  async function submitDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("direct");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/direct-opportunities/`, { method:"POST", credentials:"include", headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"}, body:JSON.stringify({ title:form.get("title"), employer_name:form.get("employer_name"), opportunity_type:form.get("opportunity_type"), domain:form.get("domain"), province:form.get("province"), importance:form.get("importance"), next_action:"", stage:"new" }) });
      const payload = await response.json() as ApiDirectOpportunity & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "ثبت ارجاع مستقیم انجام نشد.");
      directCache.current.clear(); setDirectRefresh((value) => value + 1); setDashboardRefresh((value) => value + 1);
      setDirectModal(false); notify("ارجاع مستقیم در پایگاه‌داده ثبت شد.");
    } catch (error) { notify(error instanceof Error ? error.message : "ثبت ارجاع مستقیم انجام نشد."); } finally { setBusy(""); }
  }

  const urgencyOptions = <><option value="">همه فوریت‌ها</option><option value="critical">بحرانی یا گذشته</option><option value="high">زیاد</option><option value="medium">متوسط</option><option value="normal">عادی</option><option value="unknown">تاریخ نامشخص</option></>;

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}><div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1></div><Link href="/">بازگشت به سامانه</Link></header>

    <div className={styles.banner} style={{borderColor: mode === "live" ? "#86d4b2" : mode === "error" ? "#efb3aa" : "#d8c26e", background: mode === "live" ? "#ecfdf5" : mode === "error" ? "#fff1ef" : "#fff8d9"}}>
      <b>{mode === "live" ? "داده واقعی" : mode === "loading" ? "در حال اتصال" : mode === "unauthorized" ? "نیازمند ورود" : "خطای ارتباط"}</b>
      <span>{mode === "live" ? `متصل به PostgreSQL${username ? ` با کاربر ${username}` : ""}` : mode === "loading" ? "در حال بررسی نشست سامانه..." : mode === "unauthorized" ? "برای مشاهده و اجرای استخراج وارد سامانه شوید." : "داده نمونه نمایش داده نمی‌شود؛ ارتباط API را بررسی کنید."}</span>
    </div>

    {message && <div className={styles.message}>{message}</div>}
    {mode === "unauthorized" && <article className={styles.panel} style={{maxWidth:520,margin:"18px auto"}}><h2>ورود به PDP One</h2><p>برای جلوگیری از نمایش داده نمونه، این صفحه فقط پس از ورود اطلاعات واقعی را نشان می‌دهد.</p><form onSubmit={submitLogin} className={styles.fields}><label>نام کاربری<input name="username" autoComplete="username" required /></label><label>رمز عبور<input name="password" type="password" autoComplete="current-password" required /></label><button className={styles.primaryButton} disabled={busy === "login"}>{busy === "login" ? "در حال ورود..." : "ورود"}</button></form></article>}
    {mode === "error" && <article className={styles.panel} style={{maxWidth:720,margin:"18px auto"}}><h2>ارتباط با API برقرار نشد</h2><p>هیچ داده نمونه‌ای جایگزین نشده است. پس از بررسی سرویس Backend، دکمه زیر را بزنید.</p><button className={styles.primaryButton} onClick={() => setRefresh((value) => value + 1)}>تلاش مجدد</button></article>}
    {mode === "loading" && <article className={styles.panel} style={{marginTop:18}}><p>در حال بررسی نشست واقعی...</p></article>}

    {mode === "live" && <>
      <nav className={styles.tabs}>{tabs.map(([id,label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); resetFilters(); setNoticeView("all"); setDirectView("all"); }}>{label}</button>)}</nav>

      {tab === "dashboard" && <section>
        {dashboardLoading && !dashboard.generated_at && <div className={styles.message}>در حال دریافت خلاصه مدیریتی...</div>}
        <div className={styles.kpis}>
          <article className={styles.kpi}><span>فراخوان جدید</span><b style={{fontSize:21,lineHeight:1.15}}>{fa.format(metric("new_today"))}</b><small>امروز</small></article>
          <article className={styles.kpi}><span>تحلیل‌نشده</span><b>{fa.format(metric("analysis_remaining"))}</b><small>در انتظار تحلیل</small></article>
          <article className={styles.kpi}><span>پیشنهادی</span><b>{fa.format(recommendedCount)}</b><small>نیازمند تصمیم انسانی</small></article>
          <article className={styles.kpi}><span>منتخب</span><b>{fa.format(selectedCount)}</b><small>پرونده در جریان</small></article>
          <article className={styles.kpi}><span>ارسال‌شده</span><b>{fa.format(submittedCount)}</b><small>در انتظار نتیجه</small></article>
          <article className={styles.kpi}><span>نزدیک مهلت</span><b>{fa.format(urgentCount)}</b><small>نیازمند اقدام فوری</small></article>
          <article className={styles.kpi}><span>ارجاع مستقیم فعال</span><b>{fa.format(dashboard.management?.direct_active || 0)}</b><small>ثبت اولیه تا ارسال</small></article>
          <article className={styles.kpi}><span>نتیجه موفق</span><b>{fa.format(wonCount)}</b><small>بر اساس نتایج ثبت‌شده</small></article>
        </div>
        <div className={styles.dashboardGrid}>
          <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>{fa.format(dashboard.management?.overdue_actions || 0)} اقدام پیگیری عقب‌افتاده</span><span>{fa.format(dashboard.management?.without_responsible || 0)} پرونده بدون مسئول</span><span>{fa.format(urgentCount)} پرونده نزدیک به مهلت</span></div></article>
          <article className={styles.panel}><h2>قیف مدیریتی</h2><div className={styles.funnel}><span>استخراج و ثبت‌شده {fa.format(metric("all_notices"))}</span><span>پیشنهادی {fa.format(recommendedCount)}</span><span>منتخب {fa.format(selectedCount)}</span><span>ارسال‌شده {fa.format(submittedCount)}</span><span>نتیجه موفق {fa.format(wonCount)}</span></div></article>
          <article className={styles.panel}><h2>برد و باخت</h2><div className={styles.outcomeGrid}><div><b>{fa.format(wonCount)}</b><span>موفق</span></div><div><b>{fa.format(lostCount)}</b><span>ناموفق</span></div><div><b>{fa.format(winRate)}٪</b><span>نرخ موفقیت</span></div><div><b>{fa.format(dashboardSelected + dashboardSubmitted)}</b><span>پرونده فعال</span></div></div></article>
          <article className={styles.panel}><h2>جمع‌بندی مدیریتی ChatGPT</h2><p>{metric("all_notices") ? `${fa.format(metric("all_notices"))} فراخوان واقعی و ${fa.format(dashboard.management?.direct_total || 0)} ارجاع مستقیم در پایگاه‌داده موجود است. ${fa.format(urgentCount)} مورد نزدیک به مهلت است.` : "هنوز فراخوانی استخراج نشده است. پس از اجرای اولین استخراج، جمع‌بندی مدیریتی بر مبنای داده واقعی تکمیل می‌شود."}</p><div className={styles.summaryTags}><span>داده واقعی: {fa.format(metric("all_notices"))}</span><span>نیازمند تصمیم: {fa.format(recommendedCount)}</span><span>نزدیک مهلت: {fa.format(urgentCount)}</span></div></article>
        </div>
        <article className={`${styles.panel} ${styles.activeCases}`}><div className={styles.sectionHeading}><div><span>انتهای داشبورد</span><h2>پرونده‌های فعال</h2></div><small>مناقصات، استعلامات و ارجاعات مستقیم منتخب یا ارسال‌شده</small></div>{activeCases.length ? <div className={styles.caseTable}>{activeCases.map((item) => { const u=urgency(item.deadline); return <button key={`${item.kind}-${item.id}`}><span><b>{item.title}</b><small>{item.subtitle}</small></span><span><b>{item.stage}</b><small>پرونده واقعی</small></span><span className={`${styles.urgency} ${styles[u.tone]}`}><b>{u.label}</b><small>{u.remaining}</small></span></button>; })}</div> : <div className={styles.empty}>پرونده فعالی ثبت نشده است.</div>}</article>
      </section>}

      {(tab === "tenders" || tab === "inquiries") && <section data-pdp-shared-notice-layout={tab}>
        <div className={`${styles.views} pdp-v9-workflow-row`}>{noticeViews.map(([id,label]) => <button key={id} className={noticeView === id ? styles.active : ""} onClick={() => { setNoticeView(id); setNoticePage(1); }}>{label}</button>)}<ProcurementV9NativeToolbar /></div>
        <div className="pdp-v9-filter-bar" style={filterStyle}>
          <label>جست‌وجو<input style={inputStyle} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، استان یا کد" /></label>
          <label className="pdp-v9-native-filter">منبع<select style={inputStyle} value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">همه منابع</option>{[...new Set(notices.map((item) => item.source_name).filter(Boolean))].map((source) => <option key={source}>{source}</option>)}</select></label>
          <label>استان<select style={inputStyle} value={provinceFilter} onChange={(event) => setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(notices.map((item) => item.province).filter(Boolean))].map((province) => <option key={province}>{province}</option>)}</select></label>
          <label className="pdp-v9-native-filter">اهمیت<select style={inputStyle} value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="pdp-v9-native-filter">فوریت<select style={inputStyle} value={urgencyFilter} onChange={(event) => setUrgencyFilter(event.target.value)}>{urgencyOptions}</select></label>
          <ProcurementV9NativeFilters noticeTab />
          <div className="pdp-v2-clear-group" style={{display:"flex",alignItems:"end",gap:7}}><button className={styles.secondaryButton} onClick={clearVisibleFilters}>پاک‌کردن</button><b className="pdp-v2-row-count">{fa.format(noticeCount)}</b></div>
        </div>
        {noticeError && <div className={styles.message}>{noticeError}</div>}
        <div className={styles.recordList}>{filteredNotices.length ? filteredNotices.map((item,index) => { const u=urgency(item.submission_deadline); const selecting=selectingNoticeIds.has(item.id); return <article className={styles.record} style={compactRecordStyle} data-pdp-notice-id={item.id} key={item.id}>
          <div><div className={styles.recordTop}><small><b>ردیف {fa.format((noticePage-1)*noticePageSize+index+1)}</b>{item.reference_code && noticeView !== "all" && noticeView !== "recommended" && <> · <span className={styles.codeBadge}>{item.reference_code}</span></>} · انتشار {formatDate(item.published_date)}</small><div style={{display:"flex",gap:5,alignItems:"center",marginInlineStart:"auto",flexWrap:"wrap"}}>{item.source_url || item.detail_url ? <a href={item.detail_url || item.source_url} target="_blank" rel="noreferrer" style={sourceBadgeStyle}>{item.source_name || "منبع"}</a> : <span style={sourceBadgeStyle}>{item.source_name || "منبع نامشخص"}</span>}<span style={{...importanceBadgeBase,...importanceStyles[item.importance]}}>اهمیت {item.importance_label || importanceLabels[item.importance]}</span><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span><button className={styles.secondaryButton} style={compactViewStyle} onClick={() => setDetail({kind:"notice",item})}>مشاهده</button></div></div><h3 style={{margin:"4px 0 2px",fontSize:17}}>{item.title}</h3><p>{item.employer_name || "کارفرما نامشخص"}</p><div className={styles.facts} style={{marginTop:5,gap:5}}>{item.province && <span>{item.province}</span>}<span>{u.remaining}</span><span>پردازش: {item.processing_status_label}</span>{(item.submission_document_count || 0) > 0 && <span>{fa.format(item.submission_document_count || 0)} سند</span>}</div></div>
          <div className={styles.decision} style={compactDecisionStyle}><span className={styles.stage}>{item.case_stage_label || (item.is_recommended ? "پیشنهادی" : allLabel(tab))}</span><dl style={{margin:0}}><div style={{padding:"2px 0"}}><dt>مسئول</dt><dd>{item.case_responsible_username || "تعیین نشده"}</dd></div></dl>{!item.case_stage && <div className={styles.actions}><button className={styles.primaryButton} style={{padding:"6px 9px"}} disabled={selecting} onClick={() => selectNotice(item)}>{selecting ? "در حال ثبت..." : "انتخاب"}</button></div>}</div>
        </article>; }) : <div className={styles.empty}>{noticeLoading ? "در حال دریافت این صفحه..." : "رکورد واقعی مطابق این فیلتر وجود ندارد."}</div>}</div>
        <PaginationControls page={noticePage} pageSize={noticePageSize} count={noticeCount} loading={noticeLoading} onPage={setNoticePage} onPageSize={(size) => { setNoticePageSize(size); setNoticePage(1); }} />
      </section>}

      {tab === "direct" && <section data-pdp-shared-notice-layout="direct">
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,flexWrap:"wrap",marginBottom:10}}><div className={`${styles.views} pdp-v9-workflow-row`} style={{marginBottom:0}}>{directViews.map(([id,label]) => <button key={id} className={directView === id ? styles.active : ""} onClick={() => { setDirectView(id); setDirectPage(1); }}>{label}</button>)}<ProcurementV9NativeToolbar /></div><button className={styles.primaryButton} onClick={() => setDirectModal(true)}>ثبت ارجاع مستقیم جدید</button></div>
        <div className="pdp-v9-filter-bar" style={filterStyle}><label>جست‌وجو<input style={inputStyle} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، حوزه یا کد" /></label><label>نوع ارجاع<select style={inputStyle} value={directTypeFilter} onChange={(event) => setDirectTypeFilter(event.target.value)}><option value="">همه انواع</option>{[...new Map(directReferrals.map((item) => [item.opportunity_type,item.opportunity_type_label])).entries()].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>استان<select style={inputStyle} value={provinceFilter} onChange={(event) => setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(directReferrals.map((item) => item.province).filter(Boolean))].map((province) => <option key={province}>{province}</option>)}</select></label><label className="pdp-v9-native-filter">اهمیت<select style={inputStyle} value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="pdp-v9-native-filter">فوریت<select style={inputStyle} value={urgencyFilter} onChange={(event) => setUrgencyFilter(event.target.value)}>{urgencyOptions}</select></label><ProcurementV9NativeFilters noticeTab={false} /><b className="pdp-v2-row-count" style={{alignSelf:"end"}}>{fa.format(directCount)} رکورد</b></div>
        {directError && <div className={styles.message}>{directError}</div>}
        <div className={styles.recordList}>{filteredDirect.length ? filteredDirect.map((item,index) => { const u=urgency(item.next_action_due); return <article className={`${styles.record} pdp-v2-record`} style={compactRecordStyle} data-pdp-direct-id={item.id} key={item.id}><div className="pdp-v2-content"><div className={`${styles.recordTop} pdp-v2-record-top`}><small><b>ردیف {fa.format((directPage-1)*directPageSize+index+1)}</b>{item.reference_code && directView !== "all" && <> · <span className={styles.codeBadge}>{item.reference_code}</span></>} · {item.opportunity_type_label}</small><button className={styles.secondaryButton} style={compactViewStyle} onClick={() => setDetail({kind:"direct",item})}>مشاهده</button></div><h3 className="pdp-v2-title" style={{margin:"4px 0 2px",fontSize:17}}>{item.title}</h3><p className="pdp-v2-employer">{item.employer_name || "کارفرما نامشخص"}</p><div className="pdp-v2-meta" data-pdp-v2-meta="1"><div className="pdp-v2-meta-row pdp-v2-status-row"><span className={styles.stage}>{item.stage_label}</span><span style={{...importanceBadgeBase,...importanceStyles[item.importance]}}>اهمیت {item.importance_label || importanceLabels[item.importance]}</span><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><div className="pdp-v2-meta-row pdp-v2-source-row"><span style={sourceBadgeStyle}>ارجاع مستقیم</span>{item.business_opportunity_type_label && <span className="pdp-compact-chip pdp-preview-classification-badge">{item.business_opportunity_type_label}</span>}{item.activity_domain_label && <span className="pdp-compact-chip pdp-preview-classification-badge">{item.activity_domain_label}</span>}</div><div className="pdp-v2-meta-row pdp-v2-info-row">{item.province && <span className="pdp-compact-chip">{item.province}</span>}<span className="pdp-compact-chip">{u.remaining}</span>{item.probability_percent !== null && <span className="pdp-compact-chip">احتمال تبدیل: {fa.format(item.probability_percent)}٪</span>}</div></div></div><div className={`${styles.decision} pdp-v2-decision`} style={compactDecisionStyle}><dl style={{margin:0}}><div style={{padding:"2px 0"}}><dt>مسئول</dt><dd>{item.responsible_username || "تعیین نشده"}</dd></div></dl></div></article>; }) : <div className={styles.empty}>{directLoading ? "در حال دریافت این صفحه..." : "ارجاع مستقیم واقعی مطابق این فیلتر وجود ندارد."}</div>}</div>
        <PaginationControls page={directPage} pageSize={directPageSize} count={directCount} loading={directLoading} onPage={setDirectPage} onPageSize={(size) => { setDirectPageSize(size); setDirectPage(1); }} />
      </section>}

      {tab === "management" && <section>
        <div className={styles.managementTabs}>{managementTabs.map(([id,label]) => <button key={id} className={managementView === id ? styles.active : ""} onClick={() => setManagementView(id)}>{label}</button>)}</div>
        {managementView === "extraction" && <div style={{display:"grid",gap:14}}><article className={styles.panel}><div className={styles.sectionHeading}><div><span>داده واقعی</span><h2>منابع استخراج</h2></div><small>{fa.format(enabledConnectors.length)} Connector فعال</small></div><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:12}}>{sources.map((source) => <section key={source.id} style={{border:"1px solid #e2e8f0",borderRadius:14,padding:12,background:"#f8fafc"}}><div style={{display:"flex",justifyContent:"space-between",gap:8}}><strong>{source.name}</strong><small>{source.enabled ? "فعال" : "غیرفعال"}</small></div><div style={{display:"grid",gap:8,marginTop:10}}>{source.connectors.map((connector) => <label key={connector.id} style={{display:"flex",alignItems:"center",gap:8,padding:9,borderRadius:10,background:connector.enabled ? "#ecfdf5" : "#fff7ed"}}><input type="checkbox" checked={connector.enabled} disabled={updatingConnector === connector.id} onChange={() => toggleConnector(source.id,connector)} /><span>{connector.notice_type_label}</span><small style={{marginInlineStart:"auto"}}>{updatingConnector === connector.id ? "در حال ذخیره" : connector.status_label}</small></label>)}</div></section>)}</div>{!sources.length && <div className={styles.empty}>هیچ منبعی در پایگاه‌داده ثبت نشده است.</div>}</article><div className={styles.managementGrid}><article className={styles.panel}><h2>زمان‌بندی استخراج افزایشی</h2><div className={styles.scheduleGrid}><label>وضعیت<select value={schedule.enabled ? "enabled" : "disabled"} onChange={(event) => setSchedule({...schedule,enabled:event.target.value === "enabled"})}><option value="enabled">فعال</option><option value="disabled">غیرفعال</option></select></label><label>نوع برنامه<select value={schedule.cadence} onChange={(event) => setSchedule({...schedule,cadence:event.target.value as "daily" | "hourly"})}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label>{schedule.cadence === "daily" ? <label>ساعت روزانه<input type="time" value={schedule.dailyTime} onChange={(event) => setSchedule({...schedule,dailyTime:event.target.value})} /></label> : <label>هر چند ساعت<input type="number" min="1" max="168" value={schedule.intervalHours} onChange={(event) => setSchedule({...schedule,intervalHours:Number(event.target.value)})} /></label>}</div><p>اجرای روزانه، ساعتی و «استخراج اکنون» افزایشی هستند. وضعیت ذخیره‌شده: {automation ? (automation.enabled ? "فعال" : "غیرفعال") : "هنوز دریافت/ثبت نشده"}{automation?.next_extraction_at ? ` · اجرای بعدی: ${formatDateTime(automation.next_extraction_at)}` : ""}.</p><p>تغییرات فقط با «ذخیره زمان‌بندی» اعمال می‌شوند؛ ذخیره کردن، استخراج فوری اجرا نمی‌کند.</p><div className={styles.actions}><button className={styles.secondaryButton} disabled={busy === "automation"} onClick={saveAutomation}>{busy === "automation" ? "در حال ذخیره..." : "ذخیره زمان‌بندی"}</button><button className={styles.primaryButton} disabled={busy === "extract-incremental" || Boolean(activeRun)} onClick={() => runExtraction("incremental")}>{activeRun ? "استخراج در حال اجراست" : busy === "extract-incremental" ? "در حال ثبت..." : "استخراج اکنون"}</button></div></article><article className={styles.panel}><h2>استخراج دستی بازه گذشته</h2><label>تعداد روز گذشته<input type="number" min="1" max="365" value={schedule.lookbackDays} onChange={(event) => setSchedule({...schedule,lookbackDays:Number(event.target.value)})} /></label><p>در این حالت رسیدن به داده مشترک باعث توقف نمی‌شود و کل بازه تعیین‌شده دوباره بررسی می‌شود.</p><button className={styles.primaryButton} disabled={busy === "extract-manual_range" || Boolean(activeRun)} onClick={() => runExtraction("manual_range")}>{activeRun ? "استخراج در حال اجراست" : busy === "extract-manual_range" ? "در حال ثبت..." : "اجرای بازه‌دار"}</button></article></div></div>}
        {managementView === "reports" && <div style={{display:"grid",gap:14}}><ConnectorHealthBanner embedded /><article className={styles.panel}><div className={styles.sectionHeading}><div><span>سوابق اجرا</span><h2>آخرین استخراج‌ها</h2></div><small>تعداد صفحه، رکورد و نتیجه واقعی هر اجرا</small></div><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{["زمان","منبع","نوع","صفحه","رکورد","جدید","به‌روزشده","تکراری","وضعیت"].map((head) => <th key={head} style={{textAlign:"right",padding:9,borderBottom:"1px solid #e2e8f0"}}>{head}</th>)}</tr></thead><tbody>{extractionRows.map((run) => <tr key={run.key}><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.time}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.source}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.type}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.pages)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.records)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.fresh)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.updated)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.duplicate)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9",fontWeight:700}}>{run.status}</td></tr>)}</tbody></table>{!extractionRows.length && <div className={styles.empty}>هنوز استخراج واقعی ثبت نشده است.</div>}</div></article></div>}
        {managementView === "prompts" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>نقش و Prompt</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>نقش تحلیلگر<textarea rows={4} defaultValue="تحلیلگر ارشد مناقصات، استعلامات و فرصت‌های کسب‌وکار شرکت مهندسین مشاور طرح و برنامه پارس" /></label><label>دستورهای پایه<textarea rows={5} defaultValue="تحلیل بر مبنای صلاحیت‌ها، ظرفیت اجرایی، زمان، ریسک و سوابق شرکت انجام شود." /></label><label>Prompt تحلیل<textarea rows={7} defaultValue="تناسب فرصت، مهلت، اسناد، ریسک و اقدام پیشنهادی را بررسی کن." /></label><label className={styles.fileBox}>بارگذاری مرجع Prompt<input type="file" multiple /><small>pdf، docx، txt یا md</small></label></div></article>}
        {managementView === "keywords" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>کلیدواژه‌ها</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>کلیدواژه‌های فعال<textarea rows={10} defaultValue={"خدمات مشاوره\nمطالعات\nامکان‌سنجی\nطراحی معماری\nنظارت\nطرح جامع\nتأسیسات"} /></label><label>کلیدواژه‌های حذف یا احتیاط<textarea rows={7} defaultValue={"تأمین کالا\nاجرای صرف\nخرید تجهیزات"} /></label><label className={styles.fileBox}>بارگذاری فایل کلیدواژه<input type="file" multiple /><small>txt، csv یا xlsx</small></label></div></article>}
        {managementView === "company" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>پروفایل، صلاحیت‌ها و رزومه</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>پروفایل خلاصه شرکت<textarea rows={5} defaultValue="شرکت مهندسین مشاور طرح و برنامه پارس؛ فعال در معماری، شهرسازی، تأسیسات و مطالعات امکان‌سنجی." /></label><label>صلاحیت‌ها<textarea rows={7} defaultValue="معماری، شهرسازی، تأسیسات برق و مکانیک، مطالعات جغرافیایی و برنامه‌ریزی فضایی" /></label><label>سوابق و تجربیات<textarea rows={7} defaultValue="سوابق طراحی، نظارت، طرح جامع، امکان‌سنجی و مطالعات فنی و اقتصادی" /></label><label className={styles.fileBox}>بارگذاری پروفایل یا رزومه<input type="file" multiple /><small>pdf، docx، txt یا md</small></label></div></article>}
        {managementView === "versions" && <div className={styles.managementGrid}>{[["پروفایل شرکت","نسخه ۴","۱۴۰۵/۰۵/۰۱"],["نقش و دستورهای پایه","نسخه ۶","۱۴۰۵/۰۵/۰۲"],["پرامپت تحلیل","نسخه ۵","۱۴۰۵/۰۵/۰۲"],["کلیدواژه‌ها","نسخه ۸","۱۴۰۵/۰۵/۰۳"],["رزومه و سوابق","نسخه ۳","۱۴۰۵/۰۴/۲۹"]].map(([name,version,date]) => <article className={styles.panel} key={name}><h3>{name}</h3><dl><div><dt>نسخه</dt><dd>{version}</dd></div><div><dt>تاریخ نسخه</dt><dd>{date}</dd></div><div><dt>وضعیت</dt><dd>فعال و قفل</dd></div></dl><button className={styles.secondaryButton}>مشاهده تاریخچه</button></article>)}</div>}
      </section>}
    </>}

    {directModal && <div className={styles.backdrop}><section className={styles.modal} dir="rtl"><header><div><small>ثبت در پایگاه‌داده واقعی</small><h2>ثبت ارجاع مستقیم جدید</h2></div><button onClick={() => setDirectModal(false)}>×</button></header><form className={`${styles.modalBody} ${styles.fields}`} onSubmit={submitDirect}><label>عنوان<input name="title" required /></label><label>کارفرما<input name="employer_name" /></label><label>نوع ارجاع<select name="opportunity_type" defaultValue="direct_referral"><option value="direct_referral">معرفی مستقیم</option><option value="limited_invitation">دعوت محدود</option><option value="employer_outreach">رایزنی با کارفرما</option><option value="direct_negotiation">مذاکره مستقیم</option><option value="direct_award">ترک تشریفات</option><option value="other">سایر</option></select></label><label>حوزه<input name="domain" /></label><label>استان<input name="province" /></label><label>اهمیت<select name="importance" defaultValue="medium"><option value="low">کم</option><option value="medium">متوسط</option><option value="high">زیاد</option><option value="very_high">بسیار زیاد</option></select></label><div className={styles.editorActions}><button type="button" className={styles.secondaryButton} onClick={() => setDirectModal(false)}>انصراف</button><button className={styles.primaryButton} disabled={busy === "direct"}>{busy === "direct" ? "در حال ثبت..." : "ثبت ارجاع"}</button></div></form></section></div>}
    {detail && <div className={styles.backdrop}><section className={styles.modal} dir="rtl"><header><div><small>{detail.kind === "notice" ? detail.item.notice_type_label : "ارجاع مستقیم"}</small><h2>{detail.item.title}</h2></div><button onClick={() => setDetail(null)}>×</button></header><div className={styles.modalBody}><dl>{detail.kind === "notice" ? <><div><dt>کارفرما</dt><dd>{detail.item.employer_name || "—"}</dd></div><div><dt>منبع</dt><dd>{detail.item.source_name || "—"}</dd></div><div><dt>تاریخ انتشار</dt><dd>{formatDate(detail.item.published_date)}</dd></div><div><dt>مهلت</dt><dd>{formatDateTime(detail.item.submission_deadline)}</dd></div><div><dt>وضعیت</dt><dd>{detail.item.case_stage_label || detail.item.processing_status_label}</dd></div><div><dt>اهمیت</dt><dd>{detail.item.importance_label}</dd></div></> : <><div><dt>کارفرما</dt><dd>{detail.item.employer_name || "—"}</dd></div><div><dt>نوع ارجاع</dt><dd>{detail.item.opportunity_type_label}</dd></div><div><dt>حوزه</dt><dd>{detail.item.domain || "—"}</dd></div><div><dt>استان</dt><dd>{detail.item.province || "—"}</dd></div><div><dt>وضعیت</dt><dd>{detail.item.stage_label}</dd></div><div><dt>اهمیت</dt><dd>{detail.item.importance_label}</dd></div></>}</dl></div></section></div>}
  </main>;
}
