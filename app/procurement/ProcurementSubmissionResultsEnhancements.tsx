"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT, ProcurementUiSyncDetail } from "./procurementUiSync";

type Collection<T> = T[] | { results?: T[]; next?: string | null };

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

type CaseActionItem = RawCase & {
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

type RecommendedNotice = NoticeSummary;

type ResultTarget = {
  owner: "case" | "direct";
  id: string;
  noticeId?: string;
  title: string;
  employer: string;
  kindLabel: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const CASES_API = `${PROCUREMENT_API}/cases`;
const DIRECT_API = `${PROCUREMENT_API}/direct-opportunities`;
const OPPORTUNITY_RESULTS_API = `${PROCUREMENT_API}/opportunity-results`;
const RECOMMENDED_API = `${PROCUREMENT_API}/recommended-notices`;
const ACTION_ATTRIBUTE = "data-pdp-v25-workflow-actions";
const TOOLS_TAB_ATTRIBUTE = "data-pdp-management-tools-tab";
const SUBMISSION_DIALOG_LABEL = "مدارک و ثبت ارسال";

const CASE_ACTION_STAGES = [
  "selected",
  "evaluating",
  "participate",
  "preparing",
  "ready_to_submit",
  "submitted",
  "awaiting_result",
] as const;

const CASE_RESULT_STAGES = new Set(["submitted", "awaiting_result"]);

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

async function loadCaseActions(): Promise<CaseActionItem[]> {
  const stageCollections = await Promise.all(
    CASE_ACTION_STAGES.map((stage) => fetchAll<RawCase>(`${CASES_API}/?stage=${stage}&ordering=-updated_at`, 4)),
  );
  const casesById = new Map(stageCollections.flat().map((item) => [item.id, item]));
  const details = await Promise.all(Array.from(casesById.values()).map(async (item) => {
    try {
      const notice = await fetchOne<NoticeSummary>(`${PROCUREMENT_API}/notices/${item.notice}/`);
      return {
        ...item,
        notice_title: notice.title,
        notice_employer_name: notice.employer_name,
        notice_type: notice.resolved_notice_type,
        notice_type_label: notice.notice_type_label,
      } satisfies CaseActionItem;
    } catch {
      return null;
    }
  }));
  return details.filter((item): item is CaseActionItem => Boolean(item));
}

async function loadDirectOpportunities() {
  return fetchAll<DirectOpportunity>(`${DIRECT_API}/?ordering=-last_activity_at`, 10);
}

async function loadRecommendedNotices() {
  return fetchAll<RecommendedNotice>(`${RECOMMENDED_API}/?ordering=-last_seen_at`, 20);
}

function uniqueByRow<T>(items: T[], title: (item: T) => string, employer: (item: T) => string) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = rowKey(title(item), employer(item));
    groups.set(key, [...(groups.get(key) || []), item]);
  }
  const unique = new Map<string, T>();
  groups.forEach((group, key) => { if (group.length === 1) unique.set(key, group[0]); });
  return unique;
}

function activeTopTabLabel(root: HTMLElement) {
  const nav = root.querySelector("nav");
  if (!nav) return "";
  return normalize(Array.from(nav.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => !button.hasAttribute(TOOLS_TAB_ATTRIBUTE) && Boolean(normalize(button.getAttribute("class"))),
  )?.textContent);
}

function activeWorkflowLabel(root: HTMLElement) {
  const labels = new Set([
    "کل مناقصات",
    "مناقصات ۳ روز اخیر",
    "کل استعلامات",
    "استعلامات ۳ روز اخیر",
    "کل ارجاعات مستقیم",
    "پیشنهادی",
    "منتخب",
    "ارسال‌شده",
    "نتایج",
  ]);
  return normalize(Array.from(root.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => !button.closest("nav") && labels.has(normalize(button.textContent)) && Boolean(normalize(button.getAttribute("class"))),
  )?.textContent);
}

function actionButton(kind: "primary" | "danger") {
  if (kind === "danger") {
    return "border:1px solid #fecaca;border-radius:8px;background:#fff1f2;color:#be123c;padding:6px 8px;font:inherit;font-size:11px;font-weight:700;cursor:pointer;width:100%";
  }
  return "border:1px solid #bfdbfe;border-radius:8px;background:#eff6ff;color:#1d4ed8;padding:6px 8px;font:inherit;font-size:11px;font-weight:700;cursor:pointer;width:100%";
}

function relaxSubmissionFileRequirement() {
  const dialog = document.querySelector<HTMLElement>(`[role="dialog"][aria-label="${SUBMISSION_DIALOG_LABEL}"]`);
  if (!dialog) return;
  const fileInput = dialog.querySelector<HTMLInputElement>('input[type="file"]');
  if (!fileInput) return;
  fileInput.required = false;
  fileInput.removeAttribute("required");
  const help = fileInput.parentElement?.querySelector("small");
  if (help) help.textContent = "پیوست فایل اختیاری است. در صورت نیاز می‌توانید چند فایل را هم‌زمان انتخاب کنید؛ بدون فایل نیز ثبت ارسال انجام می‌شود.";
}

export default function ProcurementSubmissionResultsEnhancements() {
  const [caseItems, setCaseItems] = useState<CaseActionItem[]>([]);
  const [directItems, setDirectItems] = useState<DirectOpportunity[]>([]);
  const [recommendedItems, setRecommendedItems] = useState<RecommendedNotice[]>([]);
  const [resultTarget, setResultTarget] = useState<ResultTarget | null>(null);
  const [resultOutcome, setResultOutcome] = useState("won");
  const [resultReason, setResultReason] = useState("");
  const [resultNotes, setResultNotes] = useState("");
  const [resultBusy, setResultBusy] = useState(false);
  const [resultMessage, setResultMessage] = useState("");
  const submissionBusy = useRef(false);

  const refresh = useCallback(() => {
    void Promise.all([loadCaseActions(), loadDirectOpportunities(), loadRecommendedNotices()])
      .then(([cases, direct, recommended]) => {
        setCaseItems(cases);
        setDirectItems(direct);
        setRecommendedItems(recommended);
      })
      .catch(() => {
        setCaseItems([]);
        setDirectItems([]);
        setRecommendedItems([]);
      });
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const handleSync = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementUiSyncDetail>).detail;
      if (!detail || detail.source === "submission-results") return;
      if (detail.noticeId || detail.directId || detail.bulkWorkspace) refresh();
    };
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
    return () => window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, handleSync);
  }, [refresh]);

  const caseByRow = useMemo(
    () => uniqueByRow(caseItems, (item) => item.notice_title, (item) => item.notice_employer_name),
    [caseItems],
  );
  const directByRow = useMemo(
    () => uniqueByRow(directItems, (item) => item.title, (item) => item.employer_name),
    [directItems],
  );
  const recommendedByRow = useMemo(
    () => uniqueByRow(recommendedItems, (item) => item.title, (item) => item.employer_name),
    [recommendedItems],
  );

  const openResult = useCallback((target: ResultTarget) => {
    setResultTarget(target);
    setResultOutcome("won");
    setResultReason("");
    setResultNotes("");
    setResultMessage("");
  }, []);

  const dismissRecommendation = useCallback(async (item: RecommendedNotice) => {
    if (!window.confirm("این پیشنهاد AI از فهرست «پیشنهادی» حذف شود؟ خود مناقصه/استعلام حذف نمی‌شود و فقط پیشنهاد فعلی AI رد می‌شود.")) return;
    try {
      const token = await csrfToken();
      const response = await fetch(`${RECOMMENDED_API}/${item.id}/dismiss/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ reason: "حذف از فهرست پیشنهادی توسط کاربر" }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "حذف از فهرست پیشنهادی انجام نشد."));
      setRecommendedItems((current) => current.filter((candidate) => candidate.id !== item.id));
      emitProcurementUiSync({ source:"submission-results", noticeId:item.id, dashboard:true });
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "حذف از فهرست پیشنهادی انجام نشد.");
    }
  }, []);

  useEffect(() => {
    const handleSubmissionWithoutFiles = async (event: Event) => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form) return;
      const dialog = form.closest<HTMLElement>(`[role="dialog"][aria-label="${SUBMISSION_DIALOG_LABEL}"]`);
      if (!dialog) return;
      const fileInput = form.querySelector<HTMLInputElement>('input[type="file"]');
      if (!fileInput || fileInput.files?.length) return;

      event.preventDefault();
      event.stopPropagation();
      if ("stopImmediatePropagation" in event) event.stopImmediatePropagation();
      if (submissionBusy.current) return;
      submissionBusy.current = true;

      try {
        const title = normalize(form.querySelector("div b")?.textContent);
        const employer = normalizeEmployer(form.querySelector("div small")?.textContent);
        const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
        const topLabel = root ? activeTopTabLabel(root) : "";
        const key = rowKey(title, employer);
        const direct = topLabel === "ارجاعات مستقیم" ? directByRow.get(key) : undefined;
        const procurementCase = topLabel !== "ارجاعات مستقیم" ? caseByRow.get(key) : undefined;
        const targetUrl = direct ? `${DIRECT_API}/${direct.id}/` : procurementCase ? `${CASES_API}/${procurementCase.id}/` : "";
        if (!targetUrl) throw new Error("پرونده متناظر برای ثبت ارسال پیدا نشد؛ اطلاعات صفحه را دوباره همگام کنید و تلاش کنید.");

        const token = await csrfToken();
        const response = await fetch(targetUrl, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
          body: JSON.stringify({ stage: "submitted" }),
        });
        if (!response.ok) throw new Error(await responseMessage(response, "ثبت ارسال بدون فایل انجام نشد."));
        if (direct) {
          const updated = await response.json() as DirectOpportunity;
          setDirectItems((current) => current.map((item) => item.id === updated.id ? updated : item));
          emitProcurementUiSync({ source:"submission-results", directId:direct.id, dashboard:true, closeSubmissionDialog:true });
        } else if (procurementCase) {
          const updated = await response.json() as RawCase;
          setCaseItems((current) => current.map((item) => item.id === updated.id ? { ...item, ...updated } : item));
          emitProcurementUiSync({ source:"submission-results", noticeId:procurementCase.notice, dashboard:true, closeSubmissionDialog:true });
        }
        window.alert("مورد بدون فایل پیوست به «ارسال‌شده» منتقل شد. هر زمان لازم باشد می‌توانید مدارک را جداگانه در پرونده نگهداری کنید.");
        submissionBusy.current = false;
      } catch (error) {
        window.alert(error instanceof Error ? error.message : "ثبت ارسال بدون فایل انجام نشد.");
        submissionBusy.current = false;
      }
    };

    document.addEventListener("submit", handleSubmissionWithoutFiles, true);
    return () => document.removeEventListener("submit", handleSubmissionWithoutFiles, true);
  }, [caseByRow, directByRow]);

  useEffect(() => {
    let frame = 0;
    let lastContext = "";
    const sync = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        relaxSubmissionFileRequirement();
        const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
        if (!root) return;
        const topLabel = activeTopTabLabel(root);
        const isDirect = topLabel === "ارجاعات مستقیم";
        const isNotice = topLabel === "مناقصات" || topLabel === "استعلامات";

        const recommendationButtons = Array.from(root.querySelectorAll<HTMLButtonElement>("button")).filter(
          (button) => !button.closest("nav") && normalize(button.textContent) === "پیشنهادی",
        );
        recommendationButtons.forEach((button) => { button.style.display = isDirect ? "none" : ""; });

        let workflowLabel = activeWorkflowLabel(root);
        if (isDirect && workflowLabel === "پیشنهادی") {
          const allDirect = Array.from(root.querySelectorAll<HTMLButtonElement>("button")).find(
            (button) => !button.closest("nav") && normalize(button.textContent) === "کل ارجاعات مستقیم",
          );
          allDirect?.click();
          return;
        }
        workflowLabel = activeWorkflowLabel(root);

        const context = `${topLabel}|${workflowLabel}`;
        if (context !== lastContext) {
          root.querySelectorAll(`[${ACTION_ATTRIBUTE}]`).forEach((node) => node.remove());
          lastContext = context;
        }

        const articles = Array.from(root.querySelectorAll<HTMLElement>("article")).filter((article) => {
          const hasViewButton = Array.from(article.querySelectorAll("button")).some((button) => normalize(button.textContent) === "مشاهده");
          return hasViewButton && Boolean(article.querySelector("h3"));
        });

        for (const article of articles) {
          const title = normalize(article.querySelector("h3")?.textContent);
          const employer = normalizeEmployer(article.querySelector("p")?.textContent);
          const decision = article.children.item(1) as HTMLElement | null;
          if (!decision || decision.querySelector(`[${ACTION_ATTRIBUTE}]`)) continue;
          const key = rowKey(title, employer);

          if (isNotice && workflowLabel === "پیشنهادی") {
            const item = recommendedByRow.get(key);
            if (!item) continue;
            const host = document.createElement("div");
            host.setAttribute(ACTION_ATTRIBUTE, `dismiss-${item.id}`);
            host.style.marginTop = "7px";
            const dismiss = document.createElement("button");
            dismiss.type = "button";
            dismiss.textContent = "حذف از پیشنهادی";
            dismiss.style.cssText = actionButton("danger");
            dismiss.onclick = () => void dismissRecommendation(item);
            host.appendChild(dismiss);
            decision.appendChild(host);
            continue;
          }

          if (isNotice && workflowLabel === "ارسال‌شده") {
            const item = caseByRow.get(key);
            if (!item || !CASE_RESULT_STAGES.has(item.stage)) continue;
            const host = document.createElement("div");
            host.setAttribute(ACTION_ATTRIBUTE, `result-case-${item.id}`);
            host.style.marginTop = "7px";
            const result = document.createElement("button");
            result.type = "button";
            result.textContent = "ثبت نتیجه";
            result.style.cssText = actionButton("primary");
            result.onclick = () => openResult({ owner:"case", id:item.id, noticeId:item.notice, title:item.notice_title, employer:item.notice_employer_name, kindLabel:item.notice_type_label });
            host.appendChild(result);
            decision.appendChild(host);
            continue;
          }

          if (isDirect && workflowLabel === "ارسال‌شده") {
            const item = directByRow.get(key);
            if (!item || item.stage !== "submitted") continue;
            const host = document.createElement("div");
            host.setAttribute(ACTION_ATTRIBUTE, `result-direct-${item.id}`);
            host.style.marginTop = "7px";
            const result = document.createElement("button");
            result.type = "button";
            result.textContent = "ثبت نتیجه";
            result.style.cssText = actionButton("primary");
            result.onclick = () => openResult({ owner:"direct", id:item.id, title:item.title, employer:item.employer_name, kindLabel:"ارجاع مستقیم" });
            host.appendChild(result);
            decision.appendChild(host);
          }
        }
      });
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "required"] });
    window.addEventListener("resize", sync);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sync);
      window.cancelAnimationFrame(frame);
      document.querySelectorAll(`[${ACTION_ATTRIBUTE}]`).forEach((node) => node.remove());
    };
  }, [caseByRow, directByRow, dismissRecommendation, openResult, recommendedByRow]);

  async function submitResult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resultTarget) return;
    if (!resultReason.trim()) {
      setResultMessage("ثبت یک توضیح یا دلیل کوتاه برای نتیجه الزامی است.");
      return;
    }
    setResultBusy(true);
    setResultMessage("");
    try {
      const token = await csrfToken();
      let response: Response;
      if (resultTarget.owner === "case") {
        response = await fetch(`${CASES_API}/${resultTarget.id}/`, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
          body: JSON.stringify({ stage: resultOutcome, decision_reason: resultReason.trim(), progress: 100 }),
        });
      } else {
        response = await fetch(`${OPPORTUNITY_RESULTS_API}/`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
          body: JSON.stringify({
            opportunity: resultTarget.id,
            outcome: resultOutcome,
            reason: resultReason.trim(),
            notes: resultNotes.trim(),
          }),
        });
      }
      if (!response.ok) throw new Error(await responseMessage(response, "ثبت نتیجه انجام نشد."));
      if (resultTarget.owner === "case") {
        setCaseItems((current) => current.filter((item) => item.id !== resultTarget.id));
        emitProcurementUiSync({ source:"submission-results", noticeId:resultTarget.noticeId, dashboard:true });
      } else {
        emitProcurementUiSync({ source:"submission-results", directId:resultTarget.id, dashboard:true });
      }
      setResultTarget(null);
      setResultReason("");
      setResultNotes("");
      window.alert("نتیجه ثبت شد و مورد به بخش «نتایج» منتقل شد.");
      refresh();
    } catch (error) {
      setResultMessage(error instanceof Error ? error.message : "ثبت نتیجه انجام نشد.");
    } finally {
      setResultBusy(false);
    }
  }

  const outcomes = resultTarget?.owner === "direct" ? directOutcomes : caseOutcomes;

  return <>
    {resultTarget && <div dir="rtl" role="dialog" aria-modal="true" aria-label="ثبت نتیجه" style={{position:"fixed",inset:0,zIndex:1750,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
      <section style={{width:"min(620px,96vw)",maxHeight:"90vh",overflow:"auto",background:"white",borderRadius:16,boxShadow:"0 24px 70px rgba(15,23,42,.35)"}}>
        <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,padding:"14px 16px",borderBottom:"1px solid #e2e8f0"}}>
          <div><small style={{color:"#64748b"}}>{resultTarget.kindLabel}</small><h2 style={{fontSize:18,margin:"3px 0 0"}}>ثبت نتیجه</h2></div>
          <button type="button" disabled={resultBusy} onClick={() => setResultTarget(null)} style={{border:0,borderRadius:9,width:36,height:36,fontSize:22,cursor:"pointer"}}>×</button>
        </header>
        <form onSubmit={submitResult} style={{display:"grid",gap:12,padding:16}}>
          <div style={{padding:"10px 12px",borderRadius:10,background:"#f8fafc",border:"1px solid #e2e8f0"}}>
            <b style={{display:"block",marginBottom:3}}>{resultTarget.title}</b>
            <small style={{color:"#64748b"}}>{resultTarget.employer || "کارفرما نامشخص"}</small>
          </div>
          <label>نتیجه<select value={resultOutcome} onChange={(event) => setResultOutcome(event.target.value)} style={{display:"block",width:"100%",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9,background:"white"}}>{outcomes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>دلیل یا توضیح نتیجه<textarea required value={resultReason} onChange={(event) => setResultReason(event.target.value)} maxLength={500} rows={3} style={{display:"block",width:"100%",boxSizing:"border-box",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9}} /></label>
          {resultTarget.owner === "direct" && <label>یادداشت تکمیلی اختیاری<textarea value={resultNotes} onChange={(event) => setResultNotes(event.target.value)} rows={3} style={{display:"block",width:"100%",boxSizing:"border-box",marginTop:5,padding:9,border:"1px solid #cbd5e1",borderRadius:9}} /></label>}
          {resultMessage && <div role="status" style={{padding:"9px 11px",borderRadius:9,background:"#fff1f2",color:"#9f1239"}}>{resultMessage}</div>}
          <div style={{padding:"9px 11px",borderRadius:9,background:"#eff6ff",color:"#1e40af",fontSize:12,lineHeight:1.8}}>پس از ثبت موفق، این مورد از «ارسال‌شده» خارج و در تب «نتایج» نمایش داده می‌شود.</div>
          <div style={{display:"flex",justifyContent:"flex-end",gap:8}}><button type="button" disabled={resultBusy} onClick={() => setResultTarget(null)} style={{border:"1px solid #cbd5e1",borderRadius:9,background:"white",padding:"8px 12px",font:"inherit"}}>انصراف</button><button type="submit" disabled={resultBusy} style={{border:0,borderRadius:9,background:"#1d4ed8",color:"white",padding:"8px 13px",font:"inherit",fontWeight:700}}>{resultBusy ? "در حال ثبت..." : "ثبت نتیجه"}</button></div>
        </form>
      </section>
    </div>}
  </>;
}
