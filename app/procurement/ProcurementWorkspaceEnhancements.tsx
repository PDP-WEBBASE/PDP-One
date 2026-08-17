"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import AIReviewCenterPanel from "./AIReviewCenterPanel";
import AnalysisContextManager from "./AnalysisContextManager";
import AnalysisEnginePanel from "./AnalysisEnginePanel";
import AutomationControlPanel from "./AutomationControlPanel";
import CaseContractDraftPanel from "./CaseContractDraftPanel";
import CaseFollowUpPanel from "./CaseFollowUpPanel";
import ManagementDashboardPanel from "./ManagementDashboardPanel";
import OpportunityWorkflowPanel from "./OpportunityWorkflowPanel";
import ProcurementAnalysisCenterPanel from "./ProcurementAnalysisCenterPanel";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type ToolKey =
  | "workflow"
  | "review"
  | "followup"
  | "contract"
  | "dashboard"
  | "automation"
  | "analysis"
  | "analysisSettings"
  | "engine";

type RawCase = {
  id: string;
  notice: string;
  stage: string;
  stage_label: string;
  submission_document_count: number;
};

type NoticeSummary = {
  id: string;
  title: string;
  employer_name: string;
  resolved_notice_type: "tender" | "inquiry";
  notice_type_label: string;
};

type SelectedCase = RawCase & {
  notice_title: string;
  notice_employer_name: string;
  notice_type: "tender" | "inquiry";
  notice_type_label: string;
};

type DirectOpportunity = {
  id: string;
  title: string;
  employer_name: string;
  stage: string;
  stage_label: string;
  opportunity_type_label: string;
};

type UploadTarget = {
  owner: "case" | "direct";
  id: string;
  title: string;
  employer: string;
  kindLabel: string;
  documentCount: number;
};

type Collection<T> = T[] | { results?: T[]; next?: string | null };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const CASES_API = `${PROCUREMENT_API}/cases`;
const DIRECT_API = `${PROCUREMENT_API}/direct-opportunities`;
const DOCUMENTS_API = `${PROCUREMENT_API}/submission-documents`;
const TOOLBAR_HOST_ID = "pdp-procurement-management-toolbar";
const ROW_ACTION_ATTRIBUTE = "data-pdp-selected-row-actions";
const TOOLS_TAB_ATTRIBUTE = "data-pdp-management-tools-tab";
const TOOLS_TAB_LABEL = "ابزارهای مدیریتی زیرسامانه";
const EXTRACTION_TAB_LABEL = "ابزارهای استخراج و تحلیل";

const PRE_SUBMISSION_STAGES = ["selected", "evaluating", "participate", "preparing", "ready_to_submit"] as const;
const SELECTABLE_DIRECT_STAGES = new Set(["new", "reviewing", "following_up", "negotiating"]);
const SELECTED_DIRECT_STAGES = new Set(["selected", "preparing"]);
const LEGACY_FLOATING_LABELS = new Set([
  "مدیریت فرصت‌ها",
  "مرکز بازبینی AI",
  "قرارداد از پرونده برنده",
  "پیگیری مسئول و موعد",
  "داشبورد مدیریتی",
  "زمان‌بندی استخراج و AI",
  "مرکز تحلیل فراخوان‌ها",
  "تنظیمات تحلیل واقعی",
  "موتور تحلیل PDP",
]);

const tools: { key: ToolKey; label: string; description: string }[] = [
  { key: "workflow", label: "مدیریت فرصت‌ها", description: "مرحله، اقدام بعدی و تصمیم انسانی" },
  { key: "followup", label: "پیگیری مسئول و موعد", description: "مسئول، موعد و پیگیری پرونده‌ها" },
  { key: "review", label: "مرکز بازبینی AI", description: "بازبینی و کنترل پیش‌نویس‌های تحلیل" },
  { key: "analysis", label: "مرکز تحلیل فراخوان‌ها", description: "اجرای تحلیل و مشاهده وضعیت پردازش" },
  { key: "engine", label: "موتور تحلیل PDP", description: "اجرای موتور تحلیل PDP و مشاهده درخواست‌ها" },
  { key: "analysisSettings", label: "تنظیمات تحلیل واقعی", description: "Prompt، کلیدواژه، پروفایل و نسخه فعال تحلیل" },
  { key: "automation", label: "زمان‌بندی استخراج و AI", description: "کنترل اجرای دوره‌ای استخراج و تحلیل" },
  { key: "dashboard", label: "داشبورد مدیریتی", description: "نمای مدیریتی و شاخص‌های کلیدی" },
  { key: "contract", label: "قرارداد از پرونده برنده", description: "ایجاد پیش‌نویس قرارداد از پرونده برنده" },
];

const documentTypes = [
  ["technical", "پیشنهاد فنی"],
  ["financial", "پیشنهاد مالی"],
  ["resume", "رزومه و سوابق"],
  ["guarantee", "تضمین و ضمانت‌نامه"],
  ["letter", "نامه و مکاتبه"],
  ["receipt", "رسید ارسال"],
  ["employer_file", "سند کارفرما"],
  ["other", "سایر"],
] as const;

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeEmployer(value: string | null | undefined) {
  const normalized = normalize(value);
  return normalized === "کارفرما نامشخص" ? "" : normalized;
}

function rowKey(title: string, employer: string) {
  return `${normalize(title)}\u0000${normalizeEmployer(employer)}`;
}

function sameOriginPath(value: string) {
  const url = new URL(value, window.location.origin);
  return `${url.pathname}${url.search}`;
}

async function fetchAll<T>(path: string, maxPages = 20): Promise<T[]> {
  const items: T[] = [];
  let next: string | null = path;
  let pages = 0;
  while (next && pages < maxPages) {
    const response = await fetch(next, { credentials: "include", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("دریافت اطلاعات تکمیلی زیرسامانه انجام نشد.");
    const payload = await response.json() as Collection<T>;
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

async function fetchOne<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("دریافت جزئیات رکورد انجام نشد.");
  return response.json() as Promise<T>;
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

async function responseMessage(response: Response, fallback: string) {
  try {
    const payload = await response.json() as { detail?: string; [key: string]: unknown };
    if (payload.detail) return String(payload.detail);
    const first = Object.values(payload).flat().find(Boolean);
    return first ? String(first) : fallback;
  } catch {
    return fallback;
  }
}

async function loadSelectedCases(): Promise<SelectedCase[]> {
  const stageCollections = await Promise.all(
    PRE_SUBMISSION_STAGES.map((stage) => fetchAll<RawCase>(`${CASES_API}/?stage=${stage}&ordering=-updated_at`, 4)),
  );
  const casesById = new Map(stageCollections.flat().map((item) => [item.id, item]));
  const cases = Array.from(casesById.values());
  const details = await Promise.all(cases.map(async (item) => {
    try {
      const notice = await fetchOne<NoticeSummary>(`${PROCUREMENT_API}/notices/${item.notice}/`);
      return {
        ...item,
        notice_title: notice.title,
        notice_employer_name: notice.employer_name,
        notice_type: notice.resolved_notice_type,
        notice_type_label: notice.notice_type_label,
      } satisfies SelectedCase;
    } catch {
      return null;
    }
  }));
  return details.filter((item): item is SelectedCase => Boolean(item));
}

async function loadDirectOpportunities() {
  return fetchAll<DirectOpportunity>(`${DIRECT_API}/?ordering=-last_activity_at`, 10);
}

async function directDocumentCount(id: string) {
  try {
    const documents = await fetchAll<{ id: string }>(`${DOCUMENTS_API}/?direct_opportunity=${id}`, 4);
    return documents.length;
  } catch {
    return 0;
  }
}

function activeWorkflowLabel(root: HTMLElement) {
  const labels = new Set(["کل مناقصات", "مناقصات ۳ روز اخیر", "کل استعلامات", "استعلامات ۳ روز اخیر", "کل ارجاعات مستقیم", "پیشنهادی", "منتخب", "ارسال‌شده", "نتایج"]);
  return normalize(Array.from(root.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => labels.has(normalize(button.textContent)) && Boolean(normalize(button.getAttribute("class"))),
  )?.textContent);
}

function activeTopTabLabel(root: HTMLElement) {
  const nav = root.querySelector("nav");
  if (!nav) return "";
  return normalize(Array.from(nav.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => !button.hasAttribute(TOOLS_TAB_ATTRIBUTE) && Boolean(normalize(button.getAttribute("class"))),
  )?.textContent);
}

function hideLegacyFloatingButtons() {
  document.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
    if (LEGACY_FLOATING_LABELS.has(normalize(button.textContent)) && button.style.position === "fixed") {
      button.dataset.pdpLegacyFloatingTool = "hidden";
      button.style.display = "none";
    }
  });
}

function ManagementToolbar({ onOpen }: { onOpen: (key: ToolKey) => void }) {
  return <section dir="rtl" style={{margin:"12px 0 16px",padding:14,border:"1px solid #dbe3ec",borderRadius:14,background:"#f8fafc",boxShadow:"0 5px 18px rgba(15,23,42,.05)"}}>
    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,marginBottom:10,flexWrap:"wrap"}}>
      <div><strong style={{display:"block",color:"#0f172a",fontSize:17}}>ابزارهای مدیریتی زیرسامانه</strong><small style={{color:"#64748b"}}>همه ابزارهای مدیریتی و تحلیل از روی لیست فراخوان‌ها جمع شده‌اند و از این تب باز می‌شوند.</small></div>
      <span style={{fontSize:11,padding:"4px 8px",borderRadius:999,background:"white",border:"1px solid #dbe3ec",color:"#475569"}}>۹ ابزار</span>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(175px,1fr))",gap:8}}>
      {tools.map((tool) => <button key={tool.key} type="button" onClick={() => onOpen(tool.key)} style={{minHeight:62,textAlign:"right",border:"1px solid #dbe3ec",borderRadius:11,background:"white",padding:"10px 11px",font:"inherit",cursor:"pointer",color:"#0f172a",boxShadow:"0 2px 7px rgba(15,23,42,.035)"}}>
        <b style={{display:"block",fontSize:12.5,marginBottom:3}}>{tool.label}</b>
        <small style={{display:"block",fontSize:10.5,lineHeight:1.7,color:"#64748b"}}>{tool.description}</small>
      </button>)}
    </div>
  </section>;
}

function ActiveToolPanel({ tool, onClose }: { tool: ToolKey | null; onClose: () => void }) {
  if (tool === "workflow") return <OpportunityWorkflowPanel onClose={onClose} />;
  if (tool === "review") return <AIReviewCenterPanel onClose={onClose} />;
  if (tool === "followup") return <CaseFollowUpPanel onClose={onClose} />;
  if (tool === "contract") return <CaseContractDraftPanel onClose={onClose} />;
  if (tool === "dashboard") return <ManagementDashboardPanel onClose={onClose} />;
  if (tool === "automation") return <AutomationControlPanel onClose={onClose} />;
  if (tool === "analysis") return <ProcurementAnalysisCenterPanel onClose={onClose} />;
  if (tool === "analysisSettings") return <AnalysisContextManager initialSection="prompts" onClose={onClose} />;
  if (tool === "engine") return <AnalysisEnginePanel onClose={onClose} />;
  return null;
}

function buttonStyle(kind: "primary" | "danger" | "muted") {
  if (kind === "primary") return "border:1px solid #bfdbfe;border-radius:8px;background:#eff6ff;color:#1d4ed8;padding:6px 7px;font:inherit;font-size:11px;font-weight:700;cursor:pointer";
  if (kind === "danger") return "border:1px solid #fecaca;border-radius:8px;background:#fff1f2;color:#be123c;padding:6px 7px;font:inherit;font-size:11px;font-weight:700;cursor:pointer";
  return "border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;color:#94a3b8;padding:6px 7px;font:inherit;font-size:11px;font-weight:700;cursor:not-allowed";
}

export default function ProcurementWorkspaceEnhancements() {
  const [toolbarHost, setToolbarHost] = useState<HTMLElement | null>(null);
  const [toolsActive, setToolsActive] = useState(false);
  const [activeTool, setActiveTool] = useState<ToolKey | null>(null);
  const [selectedCases, setSelectedCases] = useState<SelectedCase[]>([]);
  const [directItems, setDirectItems] = useState<DirectOpportunity[]>([]);
  const [directDocumentCounts, setDirectDocumentCounts] = useState<Record<string, number>>({});
  const [uploadTarget, setUploadTarget] = useState<UploadTarget | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [documentType, setDocumentType] = useState<(typeof documentTypes)[number][0]>("technical");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");

  const refreshActionData = useCallback(() => {
    void Promise.all([loadSelectedCases(), loadDirectOpportunities()]).then(async ([cases, direct]) => {
      setSelectedCases(cases);
      setDirectItems(direct);
      const selected = direct.filter((item) => SELECTED_DIRECT_STAGES.has(item.stage));
      const counts = await Promise.all(selected.map(async (item) => [item.id, await directDocumentCount(item.id)] as const));
      setDirectDocumentCounts(Object.fromEntries(counts));
    }).catch(() => {
      setSelectedCases([]);
      setDirectItems([]);
      setDirectDocumentCounts({});
    });
  }, []);

  useEffect(() => {
    refreshActionData();
    const timer = window.setInterval(refreshActionData, 30000);
    const handleClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("button") : null;
      if (normalize(target?.textContent) === "انتخاب") window.setTimeout(refreshActionData, 900);
    };
    document.addEventListener("click", handleClick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("click", handleClick);
    };
  }, [refreshActionData]);

  useEffect(() => {
    const handleSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!detail || detail.source === "workspace-enhancements") return;
      if (detail.closeSubmissionDialog) {
        setUploadTarget(null);
        setFiles([]);
        setDescription("");
        setUploadMessage("");
      }
      if (detail.noticeId || detail.directId || detail.bulkWorkspace) refreshActionData();
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
  }, [refreshActionData]);

  const selectedCaseByRow = useMemo(() => {
    const groups = new Map<string, SelectedCase[]>();
    for (const item of selectedCases) {
      const key = rowKey(item.notice_title, item.notice_employer_name);
      groups.set(key, [...(groups.get(key) || []), item]);
    }
    const unique = new Map<string, SelectedCase>();
    groups.forEach((items, key) => { if (items.length === 1) unique.set(key, items[0]); });
    return unique;
  }, [selectedCases]);

  const directByRow = useMemo(() => {
    const groups = new Map<string, DirectOpportunity[]>();
    for (const item of directItems) {
      const key = rowKey(item.title, item.employer_name);
      groups.set(key, [...(groups.get(key) || []), item]);
    }
    const unique = new Map<string, DirectOpportunity>();
    groups.forEach((items, key) => { if (items.length === 1) unique.set(key, items[0]); });
    return unique;
  }, [directItems]);

  const openUpload = useCallback((target: UploadTarget) => {
    setUploadTarget(target);
    setFiles([]);
    setDescription("");
    setUploadMessage("");
  }, []);

  const removeCase = useCallback(async (item: SelectedCase) => {
    if (item.submission_document_count > 0) return;
    if (!window.confirm("این پرونده از فهرست منتخب حذف شود؟ خود مناقصه/استعلام و سابقه تحلیل حذف نمی‌شود.")) return;
    try {
      const token = await csrfToken();
      const response = await fetch(`${CASES_API}/${item.id}/`, {
        method: "DELETE",
        credentials: "include",
        headers: { "X-CSRFToken": token, Accept: "application/json" },
      });
      if (!response.ok) throw new Error(await responseMessage(response, "حذف از منتخب انجام نشد."));
      setSelectedCases((current) => current.filter((candidate) => candidate.id !== item.id));
      emitProcurementUiSync({ source:"workspace-enhancements", noticeId:item.notice, dashboard:true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "حذف از منتخب انجام نشد.");
    }
  }, []);

  const updateDirectStage = useCallback(async (item: DirectOpportunity, stage: "selected" | "reviewing") => {
    try {
      const token = await csrfToken();
      const response = await fetch(`${DIRECT_API}/${item.id}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ stage }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, stage === "selected" ? "انتخاب ارجاع مستقیم انجام نشد." : "حذف از منتخب انجام نشد."));
      const updated = await response.json() as DirectOpportunity;
      setDirectItems((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate));
      emitProcurementUiSync({ source:"workspace-enhancements", directId:item.id, dashboard:true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "تغییر مرحله ارجاع مستقیم انجام نشد.");
    }
  }, []);

  useEffect(() => {
    let frame = 0;
    let lastContext = "";
    const sync = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        hideLegacyFloatingButtons();
        const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
        if (!root) return;
        const nav = root.querySelector("nav");
        if (!nav) return;

        const nativeButtons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button")).filter((button) => !button.hasAttribute(TOOLS_TAB_ATTRIBUTE));
        const managementButton = nativeButtons.find((button) => ["مدیریت زیرسامانه", EXTRACTION_TAB_LABEL].includes(normalize(button.textContent)));
        if (managementButton && normalize(managementButton.textContent) !== EXTRACTION_TAB_LABEL) managementButton.textContent = EXTRACTION_TAB_LABEL;

        let toolsButton = nav.querySelector<HTMLButtonElement>(`button[${TOOLS_TAB_ATTRIBUTE}]`);
        if (!toolsButton) {
          toolsButton = document.createElement("button");
          toolsButton.type = "button";
          toolsButton.setAttribute(TOOLS_TAB_ATTRIBUTE, "1");
          toolsButton.textContent = TOOLS_TAB_LABEL;
          toolsButton.onclick = () => setToolsActive(true);
          nav.insertBefore(toolsButton, managementButton || null);
        }

        let host = document.getElementById(TOOLBAR_HOST_ID) as HTMLElement | null;
        if (!host) {
          host = document.createElement("div");
          host.id = TOOLBAR_HOST_ID;
          nav.insertAdjacentElement("afterend", host);
        }
        setToolbarHost((current) => current === host ? current : host);

        if (toolsActive) {
          const activeNative = nativeButtons.find((button) => Boolean(normalize(button.getAttribute("class"))));
          const activeClass = activeNative?.className || toolsButton.dataset.pdpActiveClass || "";
          if (activeClass) toolsButton.dataset.pdpActiveClass = activeClass;
          nativeButtons.forEach((button) => { if (button.className) button.className = ""; });
          if (toolsButton.className !== activeClass) toolsButton.className = activeClass;
          Array.from(root.children).filter((child) => child.tagName === "SECTION").forEach((section) => { (section as HTMLElement).style.display = "none"; });
          host.style.display = "block";
        } else {
          if (toolsButton.className) toolsButton.className = "";
          Array.from(root.children).filter((child) => child.tagName === "SECTION").forEach((section) => { (section as HTMLElement).style.display = ""; });
          host.style.display = "none";
        }

        const topLabel = activeTopTabLabel(root);
        const workflowLabel = activeWorkflowLabel(root);
        const context = `${topLabel}|${workflowLabel}|${toolsActive}`;
        if (context !== lastContext) {
          root.querySelectorAll(`[${ROW_ACTION_ATTRIBUTE}]`).forEach((node) => node.remove());
          lastContext = context;
        }
        if (toolsActive) return;

        const isDirect = topLabel === "ارجاعات مستقیم";
        const isNotice = topLabel === "مناقصات" || topLabel === "استعلامات";
        const articles = Array.from(root.querySelectorAll<HTMLElement>("article")).filter((article) => {
          const hasViewButton = Array.from(article.querySelectorAll("button")).some((button) => normalize(button.textContent) === "مشاهده");
          return hasViewButton && Boolean(article.querySelector("h3"));
        });

        for (const article of articles) {
          const title = normalize(article.querySelector("h3")?.textContent);
          const employer = normalizeEmployer(article.querySelector("p")?.textContent);
          const decision = article.children.item(1) as HTMLElement | null;
          if (!decision) continue;

          if (isNotice && workflowLabel === "منتخب") {
            const item = selectedCaseByRow.get(rowKey(title, employer));
            if (!item || decision.querySelector(`[${ROW_ACTION_ATTRIBUTE}]`)) continue;
            const hostNode = document.createElement("div");
            hostNode.setAttribute(ROW_ACTION_ATTRIBUTE, `case-${item.id}`);
            hostNode.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px";

            const upload = document.createElement("button");
            upload.type = "button";
            upload.textContent = item.submission_document_count > 0 ? `مدارک و ثبت ارسال (${item.submission_document_count})` : "مدارک و ثبت ارسال";
            upload.style.cssText = buttonStyle("primary");
            upload.onclick = () => openUpload({ owner:"case", id:item.id, title:item.notice_title, employer:item.notice_employer_name, kindLabel:item.notice_type_label, documentCount:item.submission_document_count });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = item.submission_document_count > 0 ? "حذف غیرفعال" : "حذف از منتخب";
            remove.disabled = item.submission_document_count > 0;
            remove.title = item.submission_document_count > 0 ? "برای این پرونده سند ذخیره شده و حذف آن برای حفظ سابقه مجاز نیست." : "فقط پرونده منتخب حذف می‌شود؛ خود آگهی باقی می‌ماند.";
            remove.style.cssText = buttonStyle(remove.disabled ? "muted" : "danger");
            remove.onclick = () => void removeCase(item);
            hostNode.append(upload, remove);
            decision.appendChild(hostNode);
          }

          if (isDirect) {
            const item = directByRow.get(rowKey(title, employer));
            if (!item || decision.querySelector(`[${ROW_ACTION_ATTRIBUTE}]`)) continue;
            if (["کل ارجاعات مستقیم", "پیشنهادی"].includes(workflowLabel)) {
              const hostNode = document.createElement("div");
              hostNode.setAttribute(ROW_ACTION_ATTRIBUTE, `direct-select-${item.id}`);
              hostNode.style.marginTop = "7px";
              const select = document.createElement("button");
              select.type = "button";
              if (SELECTABLE_DIRECT_STAGES.has(item.stage)) {
                select.textContent = "انتخاب";
                select.style.cssText = buttonStyle("primary") + ";width:100%";
                select.onclick = () => void updateDirectStage(item, "selected");
              } else if (SELECTED_DIRECT_STAGES.has(item.stage)) {
                select.textContent = "منتخب";
                select.disabled = true;
                select.style.cssText = buttonStyle("muted") + ";width:100%";
              } else if (item.stage === "submitted") {
                select.textContent = "ارسال‌شده";
                select.disabled = true;
                select.style.cssText = buttonStyle("muted") + ";width:100%";
              } else {
                select.textContent = item.stage_label || "مختومه";
                select.disabled = true;
                select.style.cssText = buttonStyle("muted") + ";width:100%";
              }
              hostNode.appendChild(select);
              decision.appendChild(hostNode);
            }

            if (workflowLabel === "منتخب" && SELECTED_DIRECT_STAGES.has(item.stage)) {
              const count = directDocumentCounts[item.id] || 0;
              const hostNode = document.createElement("div");
              hostNode.setAttribute(ROW_ACTION_ATTRIBUTE, `direct-${item.id}`);
              hostNode.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px";
              const upload = document.createElement("button");
              upload.type = "button";
              upload.textContent = count > 0 ? `مدارک و ثبت ارسال (${count})` : "مدارک و ثبت ارسال";
              upload.style.cssText = buttonStyle("primary");
              upload.onclick = () => openUpload({ owner:"direct", id:item.id, title:item.title, employer:item.employer_name, kindLabel:"ارجاع مستقیم", documentCount:count });
              const remove = document.createElement("button");
              remove.type = "button";
              remove.textContent = count > 0 ? "حذف غیرفعال" : "حذف از منتخب";
              remove.disabled = count > 0;
              remove.title = count > 0 ? "برای این ارجاع سند ذخیره شده و حذف از منتخب برای حفظ سابقه مجاز نیست." : "ارجاع به مرحله بررسی برمی‌گردد و خود رکورد حذف نمی‌شود.";
              remove.style.cssText = buttonStyle(remove.disabled ? "muted" : "danger");
              remove.onclick = () => { if (!remove.disabled && window.confirm("این ارجاع از منتخب خارج و به مرحله بررسی برگردد؟")) void updateDirectStage(item, "reviewing"); };
              hostNode.append(upload, remove);
              decision.appendChild(hostNode);
            }
          }
        }
      });
    };

    const handleNavClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("nav button") : null;
      if (target && !target.hasAttribute(TOOLS_TAB_ATTRIBUTE)) setToolsActive(false);
    };
    document.addEventListener("click", handleNavClick);
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    window.addEventListener("resize", sync);
    return () => {
      observer.disconnect();
      document.removeEventListener("click", handleNavClick);
      window.removeEventListener("resize", sync);
      window.cancelAnimationFrame(frame);
      document.querySelectorAll(`[${ROW_ACTION_ATTRIBUTE}]`).forEach((host) => host.remove());
      document.querySelector(`button[${TOOLS_TAB_ATTRIBUTE}]`)?.remove();
      document.getElementById(TOOLBAR_HOST_ID)?.remove();
    };
  }, [directByRow, directDocumentCounts, openUpload, removeCase, selectedCaseByRow, toolsActive, updateDirectStage]);

  async function uploadAndSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadTarget || !files.length) {
      setUploadMessage("حداقل یک فایل برای ثبت ارسال انتخاب کنید.");
      return;
    }
    setUploading(true);
    setUploadMessage("");
    try {
      const token = await csrfToken();
      for (const file of files) {
        const body = new FormData();
        if (uploadTarget.owner === "case") body.append("case", uploadTarget.id);
        else body.append("direct_opportunity", uploadTarget.id);
        body.append("document_type", documentType);
        body.append("file", file);
        if (description.trim()) body.append("description", description.trim());
        const response = await fetch(`${DOCUMENTS_API}/`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRFToken": token, Accept: "application/json" },
          body,
        });
        if (!response.ok) throw new Error(await responseMessage(response, `بارگذاری فایل ${file.name} انجام نشد.`));
      }

      const stageUrl = uploadTarget.owner === "case" ? `${CASES_API}/${uploadTarget.id}/` : `${DIRECT_API}/${uploadTarget.id}/`;
      const stageResponse = await fetch(stageUrl, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ stage: "submitted" }),
      });
      if (!stageResponse.ok) throw new Error(await responseMessage(stageResponse, "مدارک ذخیره شد اما انتقال مورد به ارسال‌شده انجام نشد."));

      if (uploadTarget.owner === "case") {
        const selectedCase = selectedCases.find((item) => item.id === uploadTarget.id);
        setSelectedCases((current) => current.filter((item) => item.id !== uploadTarget.id));
        emitProcurementUiSync({ source:"workspace-enhancements", noticeId:selectedCase?.notice, dashboard:true });
      } else {
        const updated = await stageResponse.json() as DirectOpportunity;
        setDirectItems((current) => current.map((item) => item.id === updated.id ? updated : item));
        setDirectDocumentCounts((current) => {
          const next = { ...current };
          delete next[uploadTarget.id];
          return next;
        });
        emitProcurementUiSync({ source:"workspace-enhancements", directId:uploadTarget.id, dashboard:true });
      }

      window.alert(`${files.length} فایل ذخیره شد و مورد به «ارسال‌شده» منتقل شد.`);
      setUploadTarget(null);
      setFiles([]);
      setDescription("");
      setUploadMessage("");
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : "ثبت مدارک و ارسال انجام نشد.");
    } finally {
      setUploading(false);
    }
  }

  return <>
    {toolbarHost && toolsActive && createPortal(<ManagementToolbar onOpen={setActiveTool} />, toolbarHost)}
    <ActiveToolPanel tool={activeTool} onClose={() => setActiveTool(null)} />
    {uploadTarget && <div dir="rtl" role="dialog" aria-modal="true" aria-label="مدارک و ثبت ارسال" style={{position:"fixed",inset:0,zIndex:1700,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
      <section style={{width:"min(650px,96vw)",maxHeight:"90vh",overflow:"auto",background:"white",borderRadius:16,boxShadow:"0 24px 70px rgba(15,23,42,.35)"}}>
        <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,padding:"14px 16px",borderBottom:"1px solid #e2e8f0"}}>
          <div><small style={{color:"#64748b"}}>{uploadTarget.kindLabel}</small><h2 style={{fontSize:18,margin:"3px 0 0"}}>مدارک و ثبت ارسال</h2></div>
          <button type="button" onClick={() => !uploading && setUploadTarget(null)} style={{border:0,borderRadius:9,width:36,height:36,fontSize:22,cursor:"pointer"}}>×</button>
        </header>
        <form onSubmit={uploadAndSubmit} style={{display:"grid",gap:12,padding:16}}>
          <div style={{padding:"10px 12px",borderRadius:10,background:"#f8fafc",border:"1px solid #e2e8f0"}}>
            <b style={{display:"block",marginBottom:3}}>{uploadTarget.title}</b>
            <small style={{color:"#64748b"}}>{uploadTarget.employer || "کارفرما نامشخص"}</small>
          </div>
          <label>نوع مدارک<select value={documentType} onChange={(event) => setDocumentType(event.target.value as (typeof documentTypes)[number][0])} style={{display:"block",width:"100%",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9,background:"white"}}>{documentTypes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>فایل‌ها<input type="file" multiple required accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.zip" onChange={(event) => setFiles(Array.from(event.target.files || []))} style={{display:"block",width:"100%",marginTop:5,padding:9,border:"1px dashed #94a3b8",borderRadius:9,background:"#f8fafc"}} /><small style={{color:"#64748b"}}>هر فایل حداکثر ۵۰ مگابایت. می‌توانید چند فایل را هم‌زمان انتخاب کنید.</small></label>
          <label>توضیح اختیاری<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} style={{display:"block",width:"100%",boxSizing:"border-box",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9}} /></label>
          {files.length > 0 && <div style={{fontSize:12,color:"#475569"}}>{files.length} فایل انتخاب شده است.</div>}
          {uploadMessage && <div role="status" style={{padding:"9px 11px",borderRadius:9,background:"#fff1f2",color:"#9f1239"}}>{uploadMessage}</div>}
          <div style={{padding:"9px 11px",borderRadius:9,background:"#eff6ff",color:"#1e40af",fontSize:12,lineHeight:1.8}}>پس از ذخیره موفق همه فایل‌ها، مورد به‌صورت خودکار به بخش «ارسال‌شده» منتقل می‌شود. اگر بارگذاری یکی از فایل‌ها ناموفق باشد، مرحله پرونده تغییر نمی‌کند.</div>
          <div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button type="button" disabled={uploading} onClick={() => setUploadTarget(null)} style={{border:"1px solid #cbd5e1",borderRadius:9,background:"white",padding:"8px 12px",font:"inherit"}}>انصراف</button><button type="submit" disabled={uploading} style={{border:0,borderRadius:9,background:"#1d4ed8",color:"white",padding:"8px 13px",font:"inherit",fontWeight:700}}>{uploading ? "در حال ذخیره..." : "ذخیره مدارک و ثبت ارسال"}</button></div>
        </form>
      </section>
    </div>}
  </>;
}
