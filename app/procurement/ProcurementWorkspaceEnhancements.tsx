"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import AIReviewCenterPanel from "./AIReviewCenterPanel";
import AutomationControlPanel from "./AutomationControlPanel";
import CaseContractDraftPanel from "./CaseContractDraftPanel";
import CaseFollowUpPanel from "./CaseFollowUpPanel";
import ManagementDashboardPanel from "./ManagementDashboardPanel";
import OpportunityWorkflowPanel from "./OpportunityWorkflowPanel";
import ProcurementAnalysisCenterPanel from "./ProcurementAnalysisCenterPanel";

type ToolKey = "workflow" | "review" | "followup" | "contract" | "dashboard" | "automation" | "analysis";

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

type Collection<T> = T[] | { results?: T[]; next?: string | null };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const CASES_API = `${PROCUREMENT_API}/cases`;
const DOCUMENTS_API = `${PROCUREMENT_API}/submission-documents`;
const TOOLBAR_HOST_ID = "pdp-procurement-management-toolbar";
const ROW_ACTION_ATTRIBUTE = "data-pdp-selected-row-actions";

const PRE_SUBMISSION_STAGES = new Set(["selected", "evaluating", "participate", "preparing", "ready_to_submit"]);
const LEGACY_FLOATING_LABELS = new Set([
  "مدیریت فرصت‌ها",
  "مرکز بازبینی AI",
  "قرارداد از پرونده برنده",
  "پیگیری مسئول و موعد",
  "داشبورد مدیریتی",
  "زمان‌بندی استخراج و AI",
  "مرکز تحلیل فراخوان‌ها",
]);

const tools: { key: ToolKey; label: string; description: string }[] = [
  { key: "workflow", label: "مدیریت فرصت‌ها", description: "مرحله، اقدام بعدی و تصمیم انسانی" },
  { key: "followup", label: "پیگیری مسئول و موعد", description: "مسئول، موعد و پیگیری پرونده‌ها" },
  { key: "review", label: "مرکز بازبینی AI", description: "بازبینی و کنترل پیش‌نویس‌های تحلیل" },
  { key: "analysis", label: "مرکز تحلیل فراخوان‌ها", description: "اجرای تحلیل و مشاهده وضعیت پردازش" },
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

async function fetchAll<T>(path: string, maxPages = 100): Promise<T[]> {
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
  const [cases, tenders, inquiries] = await Promise.all([
    fetchAll<RawCase>(`${CASES_API}/?ordering=-updated_at`),
    fetchAll<NoticeSummary>(`${PROCUREMENT_API}/notices/?resolved_notice_type=tender&ordering=-last_seen_at`),
    fetchAll<NoticeSummary>(`${PROCUREMENT_API}/notices/?resolved_notice_type=inquiry&ordering=-last_seen_at`),
  ]);
  const notices = [...tenders, ...inquiries];
  const noticeById = new Map(notices.map((notice) => [notice.id, notice]));
  return cases
    .filter((item) => PRE_SUBMISSION_STAGES.has(item.stage))
    .map((item) => {
      const notice = noticeById.get(item.notice);
      if (!notice) return null;
      return {
        ...item,
        notice_title: notice.title,
        notice_employer_name: notice.employer_name,
        notice_type: notice.resolved_notice_type,
        notice_type_label: notice.notice_type_label,
      } satisfies SelectedCase;
    })
    .filter((item): item is SelectedCase => Boolean(item));
}

function activeSelectedView(root: HTMLElement) {
  const selected = Array.from(root.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => normalize(button.textContent) === "منتخب" && Boolean(normalize(button.getAttribute("class"))),
  );
  return Boolean(selected);
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
  return <section dir="rtl" style={{margin:"10px 0 14px",padding:12,border:"1px solid #dbe3ec",borderRadius:14,background:"#f8fafc",boxShadow:"0 5px 18px rgba(15,23,42,.05)"}}>
    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,marginBottom:9,flexWrap:"wrap"}}>
      <div><strong style={{display:"block",color:"#0f172a"}}>ابزارهای مدیریتی زیرسامانه</strong><small style={{color:"#64748b"}}>ابزارها از روی لیست فراخوان‌ها جدا شده‌اند و فقط با انتخاب شما باز می‌شوند.</small></div>
      <span style={{fontSize:11,padding:"4px 8px",borderRadius:999,background:"white",border:"1px solid #dbe3ec",color:"#475569"}}>۷ ابزار</span>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(175px,1fr))",gap:8}}>
      {tools.map((tool) => <button key={tool.key} type="button" onClick={() => onOpen(tool.key)} style={{minHeight:58,textAlign:"right",border:"1px solid #dbe3ec",borderRadius:11,background:"white",padding:"9px 10px",font:"inherit",cursor:"pointer",color:"#0f172a",boxShadow:"0 2px 7px rgba(15,23,42,.035)"}}>
        <b style={{display:"block",fontSize:12.5,marginBottom:3}}>{tool.label}</b>
        <small style={{display:"block",fontSize:10.5,lineHeight:1.6,color:"#64748b"}}>{tool.description}</small>
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
  return null;
}

export default function ProcurementWorkspaceEnhancements() {
  const [toolbarHost, setToolbarHost] = useState<HTMLElement | null>(null);
  const [activeTool, setActiveTool] = useState<ToolKey | null>(null);
  const [selectedCases, setSelectedCases] = useState<SelectedCase[]>([]);
  const [uploadTarget, setUploadTarget] = useState<SelectedCase | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [documentType, setDocumentType] = useState<(typeof documentTypes)[number][0]>("technical");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");

  const refreshSelectedCases = useCallback(() => {
    void loadSelectedCases().then(setSelectedCases).catch(() => setSelectedCases([]));
  }, []);

  useEffect(() => {
    refreshSelectedCases();
    const timer = window.setInterval(refreshSelectedCases, 30000);
    const handleClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("button") : null;
      if (normalize(target?.textContent) === "انتخاب") {
        window.setTimeout(refreshSelectedCases, 1200);
      }
    };
    document.addEventListener("click", handleClick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("click", handleClick);
    };
  }, [refreshSelectedCases]);

  const selectedCaseByRow = useMemo(() => {
    const groups = new Map<string, SelectedCase[]>();
    for (const item of selectedCases) {
      const key = rowKey(item.notice_title, item.notice_employer_name);
      groups.set(key, [...(groups.get(key) || []), item]);
    }
    const unique = new Map<string, SelectedCase>();
    groups.forEach((items, key) => {
      if (items.length === 1) unique.set(key, items[0]);
    });
    return unique;
  }, [selectedCases]);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        hideLegacyFloatingButtons();
        const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
        if (!root) return;

        const nav = root.querySelector("nav");
        if (nav?.parentElement) {
          let host = document.getElementById(TOOLBAR_HOST_ID) as HTMLElement | null;
          if (!host) {
            host = document.createElement("div");
            host.id = TOOLBAR_HOST_ID;
            nav.insertAdjacentElement("afterend", host);
          }
          setToolbarHost((current) => current === host ? current : host);
        }

        const existingHosts = root.querySelectorAll<HTMLElement>(`[${ROW_ACTION_ATTRIBUTE}]`);
        if (!activeSelectedView(root)) {
          existingHosts.forEach((host) => host.remove());
          return;
        }

        const matchedHostIds = new Set<string>();
        const articles = Array.from(root.querySelectorAll<HTMLElement>("article")).filter((article) => {
          const hasViewButton = Array.from(article.querySelectorAll("button")).some((button) => normalize(button.textContent) === "مشاهده");
          return hasViewButton && Boolean(article.querySelector("h3"));
        });

        for (const article of articles) {
          const title = normalize(article.querySelector("h3")?.textContent);
          const employer = normalizeEmployer(article.querySelector("p")?.textContent);
          const item = selectedCaseByRow.get(rowKey(title, employer));
          if (!item) continue;
          matchedHostIds.add(item.id);
          const decision = article.children.item(1) as HTMLElement | null;
          if (!decision) continue;
          let host = decision.querySelector<HTMLElement>(`[${ROW_ACTION_ATTRIBUTE}="${item.id}"]`);
          if (host) continue;

          host = document.createElement("div");
          host.setAttribute(ROW_ACTION_ATTRIBUTE, item.id);
          host.style.display = "grid";
          host.style.gridTemplateColumns = "1fr 1fr";
          host.style.gap = "6px";
          host.style.marginTop = "7px";

          const upload = document.createElement("button");
          upload.type = "button";
          upload.textContent = item.submission_document_count > 0 ? `مدارک و ثبت ارسال (${item.submission_document_count})` : "مدارک و ثبت ارسال";
          upload.style.cssText = "border:1px solid #bfdbfe;border-radius:8px;background:#eff6ff;color:#1d4ed8;padding:6px 7px;font:inherit;font-size:11px;font-weight:700;cursor:pointer";
          upload.onclick = () => {
            setUploadTarget(item);
            setFiles([]);
            setDescription("");
            setUploadMessage("");
          };

          const remove = document.createElement("button");
          remove.type = "button";
          remove.textContent = item.submission_document_count > 0 ? "حذف غیرفعال" : "حذف از منتخب";
          remove.disabled = item.submission_document_count > 0;
          remove.title = item.submission_document_count > 0 ? "برای این پرونده سند ذخیره شده و حذف آن برای حفظ سابقه مجاز نیست." : "فقط پرونده منتخب حذف می‌شود؛ خود آگهی باقی می‌ماند.";
          remove.style.cssText = `border:1px solid ${item.submission_document_count > 0 ? "#e2e8f0" : "#fecaca"};border-radius:8px;background:${item.submission_document_count > 0 ? "#f8fafc" : "#fff1f2"};color:${item.submission_document_count > 0 ? "#94a3b8" : "#be123c"};padding:6px 7px;font:inherit;font-size:11px;font-weight:700;cursor:${item.submission_document_count > 0 ? "not-allowed" : "pointer"}`;
          remove.onclick = async () => {
            if (remove.disabled) return;
            if (!window.confirm("این پرونده از فهرست منتخب حذف شود؟ خود مناقصه/استعلام و سابقه تحلیل حذف نمی‌شود.")) return;
            remove.disabled = true;
            try {
              const token = await csrfToken();
              const response = await fetch(`${CASES_API}/${item.id}/`, {
                method: "DELETE",
                credentials: "include",
                headers: { "X-CSRFToken": token, Accept: "application/json" },
              });
              if (!response.ok) throw new Error(await responseMessage(response, "حذف از منتخب انجام نشد."));
              window.alert("پرونده از منتخب حذف شد. خود آگهی و تحلیل آن حفظ شده است.");
              window.location.reload();
            } catch (error) {
              window.alert(error instanceof Error ? error.message : "حذف از منتخب انجام نشد.");
              remove.disabled = false;
            }
          };

          host.append(upload, remove);
          decision.appendChild(host);
        }

        existingHosts.forEach((host) => {
          const id = host.getAttribute(ROW_ACTION_ATTRIBUTE) || "";
          if (!matchedHostIds.has(id)) host.remove();
        });
      });
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    window.addEventListener("resize", sync);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sync);
      window.cancelAnimationFrame(frame);
      document.querySelectorAll(`[${ROW_ACTION_ATTRIBUTE}]`).forEach((host) => host.remove());
      document.getElementById(TOOLBAR_HOST_ID)?.remove();
    };
  }, [selectedCaseByRow]);

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
        body.append("case", uploadTarget.id);
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

      const stageResponse = await fetch(`${CASES_API}/${uploadTarget.id}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ stage: "submitted" }),
      });
      if (!stageResponse.ok) throw new Error(await responseMessage(stageResponse, "مدارک ذخیره شد اما انتقال پرونده به ارسال‌شده انجام نشد."));

      window.alert(`${files.length} فایل در پرونده ذخیره شد و مورد به «ارسال‌شده» منتقل شد.`);
      window.location.reload();
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : "ثبت مدارک و ارسال انجام نشد.");
    } finally {
      setUploading(false);
    }
  }

  return <>
    {toolbarHost && createPortal(<ManagementToolbar onOpen={setActiveTool} />, toolbarHost)}
    <ActiveToolPanel tool={activeTool} onClose={() => setActiveTool(null)} />
    {uploadTarget && <div dir="rtl" role="dialog" aria-modal="true" aria-label="مدارک و ثبت ارسال" style={{position:"fixed",inset:0,zIndex:1700,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
      <section style={{width:"min(650px,96vw)",maxHeight:"90vh",overflow:"auto",background:"white",borderRadius:16,boxShadow:"0 24px 70px rgba(15,23,42,.35)"}}>
        <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,padding:"14px 16px",borderBottom:"1px solid #e2e8f0"}}>
          <div><small style={{color:"#64748b"}}>{uploadTarget.notice_type_label}</small><h2 style={{fontSize:18,margin:"3px 0 0"}}>مدارک و ثبت ارسال</h2></div>
          <button type="button" onClick={() => !uploading && setUploadTarget(null)} style={{border:0,borderRadius:9,width:36,height:36,fontSize:22,cursor:"pointer"}}>×</button>
        </header>
        <form onSubmit={uploadAndSubmit} style={{display:"grid",gap:12,padding:16}}>
          <div style={{padding:"10px 12px",borderRadius:10,background:"#f8fafc",border:"1px solid #e2e8f0"}}>
            <b style={{display:"block",marginBottom:3}}>{uploadTarget.notice_title}</b>
            <small style={{color:"#64748b"}}>{uploadTarget.notice_employer_name || "کارفرما نامشخص"}</small>
          </div>
          <label>نوع مدارک<select value={documentType} onChange={(event) => setDocumentType(event.target.value as (typeof documentTypes)[number][0])} style={{display:"block",width:"100%",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9,background:"white"}}>{documentTypes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>فایل‌ها<input type="file" multiple required accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.zip" onChange={(event) => setFiles(Array.from(event.target.files || []))} style={{display:"block",width:"100%",marginTop:5,padding:9,border:"1px dashed #94a3b8",borderRadius:9,background:"#f8fafc"}} /><small style={{color:"#64748b"}}>هر فایل حداکثر ۵۰ مگابایت. می‌توانید چند فایل را هم‌زمان انتخاب کنید.</small></label>
          <label>توضیح اختیاری<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} style={{display:"block",width:"100%",boxSizing:"border-box",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9}} /></label>
          {files.length > 0 && <div style={{fontSize:12,color:"#475569"}}>{files.length} فایل انتخاب شده است.</div>}
          {uploadMessage && <div role="status" style={{padding:"9px 11px",borderRadius:9,background:"#fff1f2",color:"#9f1239"}}>{uploadMessage}</div>}
          <div style={{padding:"9px 11px",borderRadius:9,background:"#eff6ff",color:"#1e40af",fontSize:12,lineHeight:1.8}}>پس از ذخیره موفق همه فایل‌ها، پرونده به‌صورت خودکار به بخش «ارسال‌شده» منتقل می‌شود. اگر بارگذاری یکی از فایل‌ها ناموفق باشد، مرحله پرونده تغییر نمی‌کند.</div>
          <div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button type="button" disabled={uploading} onClick={() => setUploadTarget(null)} style={{border:"1px solid #cbd5e1",borderRadius:9,background:"white",padding:"8px 12px",font:"inherit"}}>انصراف</button><button type="submit" disabled={uploading} style={{border:0,borderRadius:9,background:"#1d4ed8",color:"white",padding:"8px 13px",font:"inherit",fontWeight:700}}>{uploading ? "در حال ذخیره..." : "ذخیره مدارک و ثبت ارسال"}</button></div>
        </form>
      </section>
    </div>}
  </>;
}
