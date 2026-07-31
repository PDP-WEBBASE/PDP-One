"use client";

import { useEffect, useMemo, useState } from "react";

type ReviewSummary = {
  total: number;
  pending_review: number;
  needs_revision: number;
  reviewed: number;
  published: number;
  rejected: number;
  recommended: number;
  urgent: number;
};

type ReviewDraft = {
  id: string;
  notice: string;
  notice_title: string;
  notice_employer_name: string;
  notice_type_label: string;
  notice_province: string;
  submission_deadline: string | null;
  is_recommended: boolean;
  score: number;
  priority: string;
  priority_label: string;
  fit_for_pdp: string;
  category: string;
  reason: string;
  recommended_action: string;
  matched_experience: string[];
  risk_notes: string[];
  confidence: string | number;
  review_status: string;
  review_status_label: string;
  needs_revision: boolean;
  review_note: string;
  reviewed_by: string;
  reviewed_at: string | null;
  case_id: string | null;
  case_stage: string | null;
  case_stage_label: string | null;
  can_select: boolean;
  analyzed_at: string;
};

type Collection<T> = T[] | { results?: T[]; next?: string | null };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const fieldStyle = { width: "100%", boxSizing: "border-box", border: "1px solid #cbd5e1", borderRadius: 9, padding: 9, font: "inherit" } as const;

function sameOriginPath(value: string) {
  const url = new URL(value, window.location.origin);
  return `${url.pathname}${url.search}`;
}

async function fetchAll<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  let next: string | null = path;
  let pages = 0;
  while (next && pages < 20) {
    const response = await fetch(next, { credentials: "include", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "برای بازبینی تحلیل‌ها وارد سامانه شوید." : "دریافت تحلیل‌ها انجام نشد.");
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

async function fetchReviewData() {
  const [drafts, summaryResponse] = await Promise.all([
    fetchAll<ReviewDraft>(`${PROCUREMENT_API}/analysis-drafts/?ordering=-analyzed_at`),
    fetch(`${PROCUREMENT_API}/analysis/review-summary/`, { credentials: "include", headers: { Accept: "application/json" } }),
  ]);
  if (!summaryResponse.ok) throw new Error("دریافت شمارنده‌های بازبینی انجام نشد.");
  return { drafts, summary: await summaryResponse.json() as ReviewSummary };
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function dateLabel(value: string | null) {
  if (!value) return "ثبت نشده";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusKey(item: ReviewDraft) {
  if (item.needs_revision) return "needs_revision";
  if (item.review_status === "ai_draft") return "pending_review";
  return item.review_status;
}

const filterLabels: Record<string, string> = {
  all: "همه",
  pending_review: "در انتظار بررسی",
  needs_revision: "نیازمند تکمیل",
  reviewed: "تأییدشده",
  rejected: "ردشده",
};

export default function AIReviewCenterPanel({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<ReviewDraft[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState("pending_review");
  const [search, setSearch] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetchReviewData()
      .then(({ drafts, summary: loadedSummary }) => {
        if (!active) return;
        setItems(drafts);
        setSummary(loadedSummary);
        if (drafts[0]) setSelectedId(drafts[0].id);
      })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "دریافت تحلیل‌ها انجام نشد."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => items.filter((item) => {
    const matchesFilter = filter === "all" || statusKey(item) === filter;
    const text = `${item.notice_title} ${item.notice_employer_name} ${item.category} ${item.reason}`;
    return matchesFilter && text.includes(search.trim());
  }), [items, filter, search]);
  const selected = items.find((item) => item.id === selectedId) || filtered[0] || null;

  async function reload() {
    setLoading(true);
    setMessage("");
    try {
      const loaded = await fetchReviewData();
      setItems(loaded.drafts);
      setSummary(loaded.summary);
      if (!loaded.drafts.some((item) => item.id === selectedId) && loaded.drafts[0]) setSelectedId(loaded.drafts[0].id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "بازخوانی انجام نشد.");
    } finally {
      setLoading(false);
    }
  }

  async function review(decision: "approved" | "rejected" | "needs_revision") {
    if (!selected) return;
    if ((decision === "rejected" || decision === "needs_revision") && !note.trim()) {
      setMessage("برای رد یا بازگشت جهت تکمیل، توضیح الزامی است.");
      return;
    }
    setWorking(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis/engine/drafts/${selected.id}/review/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ decision, note: note.trim() }),
      });
      const payload = await response.json() as ReviewDraft & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "ثبت تصمیم بازبینی انجام نشد.");
      setNote("");
      await reload();
      setSelectedId(payload.id);
      setMessage(decision === "approved" ? "تحلیل تأیید شد؛ ایجاد پرونده همچنان نیازمند اقدام جداگانه است." : decision === "rejected" ? "تحلیل رد شد و دلیل در Audit ثبت گردید." : "تحلیل برای تکمیل بازگردانده شد.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ثبت تصمیم بازبینی انجام نشد.");
    } finally {
      setWorking(false);
    }
  }

  async function selectForFollowUp() {
    if (!selected) return;
    setWorking(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis/engine/drafts/${selected.id}/select/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: "{}",
      });
      const payload = await response.json() as { detail?: string; created?: boolean };
      if (!response.ok) throw new Error(payload.detail || "ایجاد پرونده منتخب انجام نشد.");
      await reload();
      setMessage(payload.created ? "پرونده منتخب ایجاد شد و برای پیگیری انسانی آماده است." : "پرونده منتخب از قبل وجود داشت و دوباره ایجاد نشد.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ایجاد پرونده منتخب انجام نشد.");
    } finally {
      setWorking(false);
    }
  }

  const stats = summary ? [
    ["کل تحلیل‌ها", summary.total],
    ["در انتظار بررسی", summary.pending_review],
    ["نیازمند تکمیل", summary.needs_revision],
    ["تأییدشده", summary.reviewed + summary.published],
    ["ردشده", summary.rejected],
  ] : [];

  return <div dir="rtl" role="dialog" aria-modal="true" aria-label="مرکز بازبینی تحلیل‌های هوش مصنوعی" style={{position:"fixed",inset:0,zIndex:1500,background:"rgba(15,23,42,.62)",display:"grid",placeItems:"center",padding:16}}>
    <section style={{width:"min(1220px,97vw)",height:"min(820px,94vh)",background:"white",borderRadius:18,boxShadow:"0 24px 75px rgba(15,23,42,.35)",display:"grid",gridTemplateRows:"auto auto 1fr",overflow:"hidden"}}>
      <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,padding:"15px 18px",borderBottom:"1px solid #e2e8f0"}}>
        <div><small style={{color:"#64748b"}}>تصمیم نهایی فقط توسط انسان</small><h2 style={{margin:"3px 0 0"}}>مرکز بازبینی تحلیل‌های هوش مصنوعی</h2></div>
        <div style={{display:"flex",gap:8}}><button type="button" onClick={() => void reload()} disabled={loading || working}>بازخوانی</button><button type="button" onClick={onClose} aria-label="بستن" style={{border:0,borderRadius:10,width:38,height:38,fontSize:24,cursor:"pointer"}}>×</button></div>
      </header>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:8,padding:"10px 16px",background:"#f8fafc",borderBottom:"1px solid #e2e8f0"}}>
        {stats.map(([label,value]) => <div key={String(label)} style={{background:"white",border:"1px solid #e2e8f0",borderRadius:10,padding:"8px 10px"}}><small style={{color:"#64748b"}}>{label}</small><b style={{display:"block",fontSize:20}}>{value}</b></div>)}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"minmax(300px,.85fr) minmax(480px,1.45fr)",minHeight:0}}>
        <aside style={{padding:13,background:"#f8fafc",borderInlineEnd:"1px solid #e2e8f0",overflow:"auto"}}>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی عنوان، کارفرما یا دلیل" style={{...fieldStyle,marginBottom:8}} />
          <div style={{display:"flex",gap:5,flexWrap:"wrap",marginBottom:10}}>{Object.entries(filterLabels).map(([key,label]) => <button key={key} type="button" onClick={() => setFilter(key)} style={{border:filter===key?"1px solid #0f766e":"1px solid #cbd5e1",background:filter===key?"#ccfbf1":"white",borderRadius:999,padding:"5px 8px",cursor:"pointer"}}>{label}</button>)}</div>
          {loading ? <p>در حال دریافت تحلیل‌های واقعی...</p> : filtered.length ? filtered.map((item) => <button key={item.id} type="button" onClick={() => { setSelectedId(item.id); setNote(item.review_note || ""); setMessage(""); }} style={{width:"100%",textAlign:"right",background:"white",border:item.id===selected?.id?"2px solid #0f766e":"1px solid #dbe3ec",borderRadius:11,padding:11,marginBottom:7,cursor:"pointer"}}>
            <b style={{display:"block",marginBottom:4}}>{item.notice_title}</b><small style={{display:"block",color:"#64748b"}}>{item.notice_employer_name || "کارفرما نامشخص"}</small><span style={{display:"inline-block",marginTop:6,padding:"2px 7px",borderRadius:999,background:item.is_recommended?"#ecfdf5":"#f1f5f9",color:item.is_recommended?"#047857":"#475569",fontSize:11}}>{item.is_recommended?"پیشنهادی":"غیرپیشنهادی"} · امتیاز {item.score} · {filterLabels[statusKey(item)] || item.review_status_label}</span>
          </button>) : <p>تحلیلی مطابق فیلتر وجود ندارد.</p>}
        </aside>
        <main style={{padding:18,overflow:"auto"}}>
          <div style={{padding:"9px 11px",borderRadius:9,background:"#fff7ed",border:"1px solid #fed7aa",color:"#9a3412",fontSize:13,marginBottom:12}}>هیچ تحلیل، انتخاب یا پرونده‌ای خودکار نهایی نمی‌شود. هر تصمیم و تبدیل فقط با اقدام صریح مدیر انجام می‌شود.</div>
          {message && <div role="status" style={{padding:"9px 11px",borderRadius:9,background:message.includes("انجام نشد")||message.includes("الزامی")?"#fff1f2":"#ecfdf5",color:message.includes("انجام نشد")||message.includes("الزامی")?"#9f1239":"#047857",marginBottom:12}}>{message}</div>}
          {!selected ? <p>یک تحلیل را انتخاب کنید.</p> : <div style={{display:"grid",gap:12}}>
            <div><small style={{color:"#64748b"}}>{selected.notice_type_label} · {selected.notice_province || "استان نامشخص"}</small><h3 style={{margin:"4px 0"}}>{selected.notice_title}</h3><p style={{margin:0,color:"#475569"}}>{selected.notice_employer_name || "کارفرما نامشخص"}</p></div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:8}}>{[["امتیاز",selected.score],["اطمینان",selected.confidence],["اولویت",selected.priority_label],["مهلت",dateLabel(selected.submission_deadline)]].map(([label,value]) => <div key={String(label)} style={{border:"1px solid #e2e8f0",borderRadius:9,padding:8}}><small style={{color:"#64748b"}}>{label}</small><b style={{display:"block"}}>{value}</b></div>)}</div>
            <section><b>تناسب با شرکت</b><p style={{whiteSpace:"pre-wrap"}}>{selected.fit_for_pdp}</p></section>
            <section><b>دلیل تحلیل</b><p style={{whiteSpace:"pre-wrap"}}>{selected.reason}</p></section>
            <section><b>اقدام پیشنهادی AI</b><p style={{whiteSpace:"pre-wrap"}}>{selected.recommended_action}</p></section>
            {!!selected.risk_notes?.length && <section><b>ریسک‌ها</b><ul>{selected.risk_notes.map((item,index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></section>}
            <label>یادداشت بازبین<textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} maxLength={1000} style={{...fieldStyle,resize:"vertical",marginTop:5}} placeholder="برای رد یا بازگشت جهت تکمیل، توضیح الزامی است." /></label>
            {selected.reviewed_by && <small style={{color:"#64748b"}}>آخرین تصمیم: {selected.reviewed_by} در {dateLabel(selected.reviewed_at)}</small>}
            <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
              <button type="button" disabled={working} onClick={() => void review("approved")} style={{padding:"9px 13px",border:0,borderRadius:9,background:"#047857",color:"white",cursor:"pointer"}}>تأیید تحلیل</button>
              <button type="button" disabled={working} onClick={() => void review("needs_revision")} style={{padding:"9px 13px",border:"1px solid #d97706",borderRadius:9,background:"#fffbeb",color:"#92400e",cursor:"pointer"}}>بازگشت برای تکمیل</button>
              <button type="button" disabled={working} onClick={() => void review("rejected")} style={{padding:"9px 13px",border:"1px solid #e11d48",borderRadius:9,background:"#fff1f2",color:"#9f1239",cursor:"pointer"}}>رد تحلیل</button>
              {selected.can_select && <button type="button" disabled={working} onClick={() => void selectForFollowUp()} style={{padding:"9px 13px",border:0,borderRadius:9,background:"#6d28d9",color:"white",cursor:"pointer"}}>ایجاد پرونده منتخب</button>}
              {selected.case_id && <span style={{padding:"9px 12px",borderRadius:9,background:"#f1f5f9"}}>پرونده موجود: {selected.case_stage_label}</span>}
            </div>
          </div>}
        </main>
      </div>
    </section>
  </div>;
}
