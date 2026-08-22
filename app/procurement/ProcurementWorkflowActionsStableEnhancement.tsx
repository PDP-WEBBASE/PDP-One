"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT } from "./procurementUiSync";
import {
  getProcurementStableViewState,
  PROCUREMENT_STABLE_VIEW_STATE_EVENT,
  stableWorkflowLabel,
  type ProcurementStableViewState,
} from "./procurementStableViewState";

type NoticeRow = {
  id: string;
  title: string;
  employer_name: string;
  notice_type_label?: string;
};

type DirectRow = {
  id: string;
  title: string;
  employer_name: string;
  opportunity_type_label?: string;
  stage: string;
  stage_label?: string;
};

type PagePayload<T> = { count?: number; results?: T[] };
type CaseMeta = { id: string; notice_id: string; stage: string; submission_document_count: number };
type WorkflowMeta = { cases?: CaseMeta[]; direct_documents?: Record<string, number> };
type UploadTarget = {
  owner: "case" | "direct";
  id: string;
  noticeId?: string;
  title: string;
  employer: string;
  kindLabel: string;
  documentCount: number;
};
type ResultTarget = {
  owner: "case" | "direct";
  id: string;
  noticeId?: string;
  title: string;
  employer: string;
  kindLabel: string;
};

type StableWindow = Window & {
  __pdpStableListCache?: Map<string, unknown>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const CASES_API = `${PROCUREMENT_API}/cases`;
const DIRECT_API = `${PROCUREMENT_API}/direct-opportunities`;
const DOCUMENTS_API = `${PROCUREMENT_API}/submission-documents`;
const RESULTS_API = `${PROCUREMENT_API}/opportunity-results`;
const RECOMMENDED_API = `${PROCUREMENT_API}/recommended-notices`;
const WORKFLOW_META_API = `${PROCUREMENT_API}/ui/workflow-page-metadata/`;
const NOTICE_DATA_EVENT = "pdp-procurement-compact-notice-data";
const DIRECT_DATA_EVENT = "pdp-procurement-direct-page-data";
const ACTION_ATTRIBUTE = "data-pdp-stable-workflow-action";
const SELECTABLE_DIRECT_STAGES = new Set(["new", "reviewing", "following_up", "negotiating"]);
const SELECTED_DIRECT_STAGES = new Set(["selected", "preparing"]);
const SUBMITTED_CASE_STAGES = new Set(["submitted", "awaiting_result"]);

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

const caseOutcomes = [
  ["won", "برنده"],
  ["lost", "بازنده"],
  ["cancelled", "لغوشده"],
  ["renewed", "تجدیدشده"],
] as const;
const directOutcomes = [
  ["won", "موفق"],
  ["lost", "ناموفق"],
  ["stopped", "متوقف‌شده"],
  ["deferred", "به تعویق افتاده"],
  ["converted_to_tender", "تبدیل به مناقصه"],
  ["converted_to_inquiry", "تبدیل به استعلام"],
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

function currentSection(state: ProcurementStableViewState) {
  if (state.top !== "tenders" && state.top !== "inquiries" && state.top !== "direct") return null;
  const expected = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
    (candidate) => !candidate.closest("nav") && normalize(candidate.textContent) === expected,
  );
  return button?.closest("section") as HTMLElement | null;
}

function actionButton(label: string, tone: "primary" | "danger" | "muted" = "primary") {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.style.cssText = tone === "danger"
    ? "width:100%;min-height:28px;border:1px solid #fecaca;border-radius:8px;background:#fff1f2;color:#be123c;padding:4px 7px;font:inherit;font-size:10.5px;font-weight:700;cursor:pointer"
    : tone === "muted"
      ? "width:100%;min-height:28px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;color:#94a3b8;padding:4px 7px;font:inherit;font-size:10.5px;font-weight:700;cursor:not-allowed"
      : "width:100%;min-height:28px;border:1px solid #bfdbfe;border-radius:8px;background:#eff6ff;color:#1d4ed8;padding:4px 7px;font:inherit;font-size:10.5px;font-weight:700;cursor:pointer";
  return button;
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

function invalidateAndRefresh(detail: { noticeId?: string; directId?: string; dashboard?: boolean } = {}) {
  (window as StableWindow).__pdpStableListCache?.clear();
  emitProcurementUiSync({ source: "stable-workflow-actions", bulkWorkspace: true, ...detail });
}

export default function ProcurementWorkflowActionsStableEnhancement() {
  const [noticeRows, setNoticeRows] = useState<NoticeRow[]>([]);
  const [directRows, setDirectRows] = useState<DirectRow[]>([]);
  const [caseMeta, setCaseMeta] = useState<Map<string, CaseMeta>>(() => new Map());
  const [directDocuments, setDirectDocuments] = useState<Record<string, number>>({});
  const [uploadTarget, setUploadTarget] = useState<UploadTarget | null>(null);
  const [resultTarget, setResultTarget] = useState<ResultTarget | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [documentType, setDocumentType] = useState<(typeof documentTypes)[number][0]>("technical");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [resultOutcome, setResultOutcome] = useState("won");
  const [resultReason, setResultReason] = useState("");
  const [resultNotes, setResultNotes] = useState("");
  const metadataRequest = useRef(0);

  const loadMetadata = useCallback(async (notices: NoticeRow[], directs: DirectRow[]) => {
    const requestVersion = ++metadataRequest.current;
    if (!notices.length && !directs.length) {
      setCaseMeta(new Map());
      setDirectDocuments({});
      return;
    }
    const params = new URLSearchParams();
    if (notices.length) params.set("notice_ids", notices.slice(0, 100).map((row) => row.id).join(","));
    if (directs.length) params.set("direct_ids", directs.slice(0, 100).map((row) => row.id).join(","));
    try {
      const response = await fetch(`${WORKFLOW_META_API}?${params.toString()}`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("metadata-unavailable");
      const payload = await response.json() as WorkflowMeta;
      if (requestVersion !== metadataRequest.current) return;
      setCaseMeta(new Map((payload.cases || []).map((item) => [item.notice_id, item])));
      setDirectDocuments(payload.direct_documents || {});
    } catch {
      if (requestVersion !== metadataRequest.current) return;
      setCaseMeta(new Map());
      setDirectDocuments({});
    }
  }, []);

  useEffect(() => {
    const onNoticeData = (event: Event) => {
      const payload = (event as CustomEvent<PagePayload<NoticeRow>>).detail;
      const rows = Array.isArray(payload?.results) ? payload.results : [];
      setNoticeRows(rows);
      setDirectRows([]);
      void loadMetadata(rows, []);
    };
    const onDirectData = (event: Event) => {
      const payload = (event as CustomEvent<PagePayload<DirectRow>>).detail;
      const rows = Array.isArray(payload?.results) ? payload.results : [];
      setDirectRows(rows);
      setNoticeRows([]);
      void loadMetadata([], rows);
    };
    const onState = () => {
      setNoticeRows([]);
      setDirectRows([]);
      setCaseMeta(new Map());
      setDirectDocuments({});
      const state = getProcurementStableViewState();
      if (state.top === "direct" && state.workflow === "recommended") {
        window.requestAnimationFrame(() => {
          const allButton = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
            (button) => !button.closest("nav") && normalize(button.textContent) === "کل ارجاعات مستقیم",
          );
          allButton?.click();
        });
      }
    };
    window.addEventListener(NOTICE_DATA_EVENT, onNoticeData);
    window.addEventListener(DIRECT_DATA_EVENT, onDirectData);
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    return () => {
      window.removeEventListener(NOTICE_DATA_EVENT, onNoticeData);
      window.removeEventListener(DIRECT_DATA_EVENT, onDirectData);
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    };
  }, [loadMetadata]);

  const noticeByRow = useMemo(() => new Map(noticeRows.map((row) => [rowKey(row.title, row.employer_name), row])), [noticeRows]);
  const noticeById = useMemo(() => new Map(noticeRows.map((row) => [row.id, row])), [noticeRows]);
  const directByRow = useMemo(() => new Map(directRows.map((row) => [rowKey(row.title, row.employer_name), row])), [directRows]);
  const directById = useMemo(() => new Map(directRows.map((row) => [row.id, row])), [directRows]);

  const removeCase = useCallback(async (meta: CaseMeta, noticeId: string) => {
    if (meta.submission_document_count > 0) return;
    if (!window.confirm("این پرونده از فهرست منتخب حذف شود؟ خود مناقصه/استعلام و سابقه تحلیل حذف نمی‌شود.")) return;
    try {
      const token = await csrfToken();
      const response = await fetch(`${CASES_API}/${meta.id}/`, { method: "DELETE", credentials: "include", headers: { "X-CSRFToken": token, Accept: "application/json" } });
      if (!response.ok) throw new Error(await responseMessage(response, "حذف از منتخب انجام نشد."));
      invalidateAndRefresh({ noticeId, dashboard: true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "حذف از منتخب انجام نشد.");
    }
  }, []);

  const updateDirectStage = useCallback(async (item: DirectRow, stage: "selected" | "reviewing") => {
    try {
      const token = await csrfToken();
      const response = await fetch(`${DIRECT_API}/${item.id}/`, {
        method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ stage }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "تغییر مرحله ارجاع مستقیم انجام نشد."));
      invalidateAndRefresh({ directId: item.id, dashboard: true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "تغییر مرحله ارجاع مستقیم انجام نشد.");
    }
  }, []);

  const dismissRecommendation = useCallback(async (item: NoticeRow) => {
    if (!window.confirm("این پیشنهاد AI از فهرست «پیشنهادی» حذف شود؟ خود مناقصه/استعلام حذف نمی‌شود و فقط پیشنهاد فعلی AI رد می‌شود.")) return;
    try {
      const token = await csrfToken();
      const response = await fetch(`${RECOMMENDED_API}/${item.id}/dismiss/`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ reason: "حذف از فهرست پیشنهادی توسط کاربر" }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "حذف از فهرست پیشنهادی انجام نشد."));
      invalidateAndRefresh({ noticeId: item.id, dashboard: true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "حذف از فهرست پیشنهادی انجام نشد.");
    }
  }, []);

  useEffect(() => {
    let frame1 = 0;
    let frame2 = 0;
    const sync = () => {
      document.querySelectorAll(`[${ACTION_ATTRIBUTE}]`).forEach((node) => node.remove());
      const state = getProcurementStableViewState();
      const section = currentSection(state);
      if (!section) return;
      const articles = Array.from(section.querySelectorAll<HTMLElement>("article")).filter((article) => Boolean(article.querySelector("h3")));
      for (const article of articles) {
        const title = normalize(article.querySelector("h3")?.textContent);
        const employer = normalize(article.querySelector("p")?.textContent);
        const decision = (article.children.item(1) as HTMLElement | null) || article;
        const key = rowKey(title, employer);
        const host = document.createElement("div");
        host.setAttribute(ACTION_ATTRIBUTE, "1");
        host.classList.add("pdp-v2-stable-actions");
        host.style.cssText = "display:grid;gap:4px;margin-top:4px";

        if (state.top === "tenders" || state.top === "inquiries") {
          const item = (article.dataset.pdpNoticeId && noticeById.get(article.dataset.pdpNoticeId)) || noticeByRow.get(key);
          if (!item) continue;
          if (state.workflow === "recommended") {
            const dismiss = actionButton("حذف از پیشنهادی", "danger");
            dismiss.onclick = () => void dismissRecommendation(item);
            host.appendChild(dismiss);
          } else if (state.workflow === "selected") {
            const meta = caseMeta.get(item.id);
            if (!meta) continue;
            const upload = actionButton(meta.submission_document_count ? `مدارک و ثبت ارسال (${meta.submission_document_count})` : "مدارک و ثبت ارسال");
            upload.onclick = () => setUploadTarget({ owner: "case", id: meta.id, noticeId: item.id, title: item.title, employer: item.employer_name, kindLabel: item.notice_type_label || "فراخوان", documentCount: meta.submission_document_count });
            const remove = actionButton(meta.submission_document_count ? "حذف غیرفعال" : "حذف از منتخب", meta.submission_document_count ? "muted" : "danger");
            remove.disabled = meta.submission_document_count > 0;
            remove.onclick = () => void removeCase(meta, item.id);
            host.append(upload, remove);
          } else if (state.workflow === "submitted") {
            const meta = caseMeta.get(item.id);
            if (!meta || !SUBMITTED_CASE_STAGES.has(meta.stage)) continue;
            const result = actionButton("ثبت نتیجه");
            result.onclick = () => setResultTarget({ owner: "case", id: meta.id, noticeId: item.id, title: item.title, employer: item.employer_name, kindLabel: item.notice_type_label || "فراخوان" });
            host.appendChild(result);
          }
        } else if (state.top === "direct") {
          const item = (article.dataset.pdpDirectId && directById.get(article.dataset.pdpDirectId)) || directByRow.get(key);
          if (!item) continue;
          const documentCount = directDocuments[item.id] || 0;
          if (state.workflow === "recent") {
            const select = actionButton(SELECTABLE_DIRECT_STAGES.has(item.stage) ? "انتخاب" : item.stage_label || "وضعیت ثبت‌شده", SELECTABLE_DIRECT_STAGES.has(item.stage) ? "primary" : "muted");
            select.disabled = !SELECTABLE_DIRECT_STAGES.has(item.stage);
            select.onclick = () => void updateDirectStage(item, "selected");
            host.appendChild(select);
          } else if (state.workflow === "selected" && SELECTED_DIRECT_STAGES.has(item.stage)) {
            const upload = actionButton(documentCount ? `مدارک و ثبت ارسال (${documentCount})` : "مدارک و ثبت ارسال");
            upload.onclick = () => setUploadTarget({ owner: "direct", id: item.id, title: item.title, employer: item.employer_name, kindLabel: item.opportunity_type_label || "ارجاع مستقیم", documentCount });
            const remove = actionButton(documentCount ? "حذف غیرفعال" : "حذف از منتخب", documentCount ? "muted" : "danger");
            remove.disabled = documentCount > 0;
            remove.onclick = () => void updateDirectStage(item, "reviewing");
            host.append(upload, remove);
          } else if (state.workflow === "submitted" && item.stage === "submitted") {
            const result = actionButton("ثبت نتیجه");
            result.onclick = () => setResultTarget({ owner: "direct", id: item.id, title: item.title, employer: item.employer_name, kindLabel: item.opportunity_type_label || "ارجاع مستقیم" });
            host.appendChild(result);
          }
        }
        if (host.childElementCount) decision.appendChild(host);
      }
    };
    const schedule = () => {
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
      frame1 = window.requestAnimationFrame(() => { frame2 = window.requestAnimationFrame(sync); });
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
    schedule();
    return () => {
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
      document.querySelectorAll(`[${ACTION_ATTRIBUTE}]`).forEach((node) => node.remove());
    };
  }, [caseMeta, directById, directByRow, directDocuments, dismissRecommendation, noticeById, noticeByRow, removeCase, updateDirectStage]);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadTarget) return;
    setBusy(true);
    try {
      const token = await csrfToken();
      for (const file of files) {
        const body = new FormData();
        if (uploadTarget.owner === "case") body.append("case", uploadTarget.id);
        else body.append("direct_opportunity", uploadTarget.id);
        body.append("document_type", documentType);
        body.append("file", file);
        if (description.trim()) body.append("description", description.trim());
        const response = await fetch(`${DOCUMENTS_API}/`, { method: "POST", credentials: "include", headers: { "X-CSRFToken": token, Accept: "application/json" }, body });
        if (!response.ok) throw new Error(await responseMessage(response, `بارگذاری فایل ${file.name} انجام نشد.`));
      }
      const stageUrl = uploadTarget.owner === "case" ? `${CASES_API}/${uploadTarget.id}/` : `${DIRECT_API}/${uploadTarget.id}/`;
      const stageResponse = await fetch(stageUrl, {
        method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ stage: "submitted" }),
      });
      if (!stageResponse.ok) throw new Error(await responseMessage(stageResponse, "انتقال مورد به ارسال‌شده انجام نشد."));
      invalidateAndRefresh({ noticeId: uploadTarget.noticeId, directId: uploadTarget.owner === "direct" ? uploadTarget.id : undefined, dashboard: true });
      window.alert(files.length ? `${files.length} فایل ذخیره شد و مورد به «ارسال‌شده» منتقل شد.` : "مورد بدون فایل پیوست به «ارسال‌شده» منتقل شد.");
      setUploadTarget(null);
      setFiles([]);
      setDescription("");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "ثبت مدارک و ارسال انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  async function submitResult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resultTarget || !resultReason.trim()) return;
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = resultTarget.owner === "case"
        ? await fetch(`${CASES_API}/${resultTarget.id}/`, {
          method: "PATCH", credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
          body: JSON.stringify({ stage: resultOutcome, decision_reason: resultReason.trim(), progress: 100 }),
        })
        : await fetch(`${RESULTS_API}/`, {
          method: "POST", credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
          body: JSON.stringify({ opportunity: resultTarget.id, outcome: resultOutcome, reason: resultReason.trim(), notes: resultNotes.trim() }),
        });
      if (!response.ok) throw new Error(await responseMessage(response, "ثبت نتیجه انجام نشد."));
      invalidateAndRefresh({ noticeId: resultTarget.noticeId, directId: resultTarget.owner === "direct" ? resultTarget.id : undefined, dashboard: true });
      setResultTarget(null);
      setResultReason("");
      setResultNotes("");
      window.alert("نتیجه ثبت شد و مورد به بخش «نتایج» منتقل شد.");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "ثبت نتیجه انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  const outcomes = resultTarget?.owner === "direct" ? directOutcomes : caseOutcomes;
  return <>
    {uploadTarget && <div dir="rtl" role="dialog" aria-modal="true" aria-label="مدارک و ثبت ارسال" style={{position:"fixed",inset:0,zIndex:1700,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
      <section style={{width:"min(650px,96vw)",maxHeight:"90vh",overflow:"auto",background:"white",borderRadius:16,boxShadow:"0 24px 70px rgba(15,23,42,.35)"}}>
        <header style={{display:"flex",justifyContent:"space-between",gap:10,padding:"14px 16px",borderBottom:"1px solid #e2e8f0"}}><div><small>{uploadTarget.kindLabel}</small><h2 style={{margin:"3px 0 0",fontSize:18}}>مدارک و ثبت ارسال</h2></div><button type="button" disabled={busy} onClick={() => setUploadTarget(null)}>×</button></header>
        <form onSubmit={submitUpload} style={{display:"grid",gap:12,padding:16}}>
          <div><b>{uploadTarget.title}</b><small style={{display:"block",color:"#64748b"}}>{uploadTarget.employer || "کارفرما نامشخص"}</small></div>
          <label>نوع مدارک<select value={documentType} onChange={(event) => setDocumentType(event.target.value as (typeof documentTypes)[number][0])} style={{display:"block",width:"100%",marginTop:5,padding:9}}>{documentTypes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>فایل‌ها (اختیاری)<input type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.zip" onChange={(event) => setFiles(Array.from(event.target.files || []))} style={{display:"block",width:"100%",marginTop:5,padding:9}}/><small>بدون فایل نیز ثبت ارسال انجام می‌شود.</small></label>
          <label>توضیح اختیاری<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} style={{display:"block",width:"100%",marginTop:5}}/></label>
          <div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button type="button" disabled={busy} onClick={() => setUploadTarget(null)}>انصراف</button><button type="submit" disabled={busy}>{busy ? "در حال ذخیره..." : "ذخیره و ثبت ارسال"}</button></div>
        </form>
      </section>
    </div>}
    {resultTarget && <div dir="rtl" role="dialog" aria-modal="true" aria-label="ثبت نتیجه" style={{position:"fixed",inset:0,zIndex:1750,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
      <section style={{width:"min(620px,96vw)",background:"white",borderRadius:16,padding:16}}><h2>ثبت نتیجه</h2><b>{resultTarget.title}</b><form onSubmit={submitResult} style={{display:"grid",gap:12,marginTop:12}}><label>نتیجه<select value={resultOutcome} onChange={(event) => setResultOutcome(event.target.value)}>{outcomes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>دلیل یا توضیح نتیجه<textarea required value={resultReason} onChange={(event) => setResultReason(event.target.value)} maxLength={500} rows={3}/></label>{resultTarget.owner === "direct" && <label>یادداشت تکمیلی<textarea value={resultNotes} onChange={(event) => setResultNotes(event.target.value)} rows={3}/></label>}<div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button type="button" disabled={busy} onClick={() => setResultTarget(null)}>انصراف</button><button type="submit" disabled={busy}>{busy ? "در حال ثبت..." : "ثبت نتیجه"}</button></div></form></section>
    </div>}
  </>;
}
