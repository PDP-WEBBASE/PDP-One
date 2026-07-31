"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type RawCase = {
  id: string;
  notice: string;
  stage: string;
  stage_label: string;
  responsible_username: string;
  next_action: string;
  next_action_due: string | null;
  progress: number;
  decision_reason: string;
  submission_document_count: number;
  updated_at: string;
};

type NoticeSummary = {
  id: string;
  title: string;
  employer_name: string;
  notice_type_label: string;
};

type CaseItem = RawCase & {
  notice_title: string;
  notice_employer_name: string;
  notice_type_label: string;
};

type CaseDraft = {
  stage: string;
  next_action: string;
  next_action_due: string;
  progress: number;
  decision_reason: string;
};

type Collection<T> = T[] | { results?: T[]; next?: string | null };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const CASES_API = `${PROCUREMENT_API}/cases`;

const stageLabels: Record<string, string> = {
  selected: "منتخب",
  evaluating: "در حال ارزیابی",
  participate: "تصمیم به شرکت یا پاسخ",
  do_not_participate: "تصمیم به عدم شرکت یا پاسخ",
  preparing: "در دست تهیه",
  ready_to_submit: "آماده ارسال",
  submitted: "ارسال‌شده",
  awaiting_result: "در انتظار نتیجه",
  won: "برنده",
  lost: "بازنده",
  cancelled: "لغوشده",
  renewed: "تجدیدشده",
};

const nextStages: Record<string, string[]> = {
  selected: ["evaluating", "do_not_participate"],
  evaluating: ["participate", "do_not_participate"],
  participate: ["preparing"],
  preparing: ["ready_to_submit"],
  ready_to_submit: ["submitted"],
  submitted: ["awaiting_result"],
  awaiting_result: ["won", "lost", "cancelled", "renewed"],
  renewed: ["evaluating"],
};

const terminalStages = new Set(["won", "lost", "cancelled", "do_not_participate"]);
const fieldStyle = { display:"block", width:"100%", boxSizing:"border-box", marginTop:5, padding:9, border:"1px solid #cbd5e1", borderRadius:9 } as const;

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
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "برای مدیریت پرونده‌ها وارد سامانه شوید." : "دریافت اطلاعات پرونده‌ها انجام نشد.");
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

async function fetchCases(): Promise<CaseItem[]> {
  const [cases, notices] = await Promise.all([
    fetchAll<RawCase>(`${CASES_API}/?ordering=-updated_at`),
    fetchAll<NoticeSummary>(`${PROCUREMENT_API}/notices/?ordering=-last_seen_at`),
  ]);
  const noticeById = new Map(notices.map((notice) => [notice.id, notice]));
  return cases.map((item) => {
    const notice = noticeById.get(item.notice);
    return {
      ...item,
      notice_title: notice?.title || "عنوان فراخوان ثبت نشده",
      notice_employer_name: notice?.employer_name || "",
      notice_type_label: notice?.notice_type_label || "فراخوان",
    };
  });
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function localInput(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function draftFor(item: CaseItem): CaseDraft {
  return {
    stage: item.stage,
    next_action: item.next_action || "",
    next_action_due: localInput(item.next_action_due),
    progress: item.progress || 0,
    decision_reason: item.decision_reason || "",
  };
}

function dateLabel(value: string | null) {
  if (!value) return "بدون موعد";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function OpportunityWorkflowPanel({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<CaseItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<CaseDraft | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    setMessage("");
    try {
      const loaded = await fetchCases();
      setItems(loaded);
      const target = loaded.find((item) => item.id === selectedId) || loaded[0];
      if (target) {
        setSelectedId(target.id);
        setDraft(draftFor(target));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "دریافت پرونده‌ها انجام نشد.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    fetchCases()
      .then((loaded) => {
        if (!active) return;
        setItems(loaded);
        if (loaded[0]) {
          setSelectedId(loaded[0].id);
          setDraft(draftFor(loaded[0]));
        }
      })
      .catch((error) => {
        if (active) setMessage(error instanceof Error ? error.message : "دریافت پرونده‌ها انجام نشد.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const selected = items.find((item) => item.id === selectedId) || null;
  const filtered = useMemo(() => items.filter((item) => `${item.notice_title} ${item.notice_employer_name} ${item.stage_label}`.includes(search.trim())), [items, search]);

  function choose(item: CaseItem) {
    setSelectedId(item.id);
    setDraft(draftFor(item));
    setMessage("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !draft) return;
    if (draft.stage === "do_not_participate" && !draft.decision_reason.trim()) {
      setMessage("برای تصمیم به عدم شرکت یا پاسخ، ثبت دلیل الزامی است.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${CASES_API}/${selected.id}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({
          stage: draft.stage,
          next_action: draft.next_action.trim(),
          next_action_due: draft.next_action_due ? new Date(draft.next_action_due).toISOString() : null,
          progress: Math.max(0, Math.min(100, Number(draft.progress) || 0)),
          decision_reason: draft.decision_reason.trim(),
        }),
      });
      const payload = await response.json() as RawCase & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "به‌روزرسانی پرونده انجام نشد.");
      const updated = { ...selected, ...payload } as CaseItem;
      setItems((current) => current.map((item) => item.id === selected.id ? updated : item));
      setDraft(draftFor(updated));
      setMessage("پرونده با موفقیت ذخیره و در Audit ثبت شد.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "به‌روزرسانی پرونده انجام نشد.");
    } finally {
      setSaving(false);
    }
  }

  const availableStages = selected ? [selected.stage, ...(nextStages[selected.stage] || [])] : [];

  return <div dir="rtl" role="dialog" aria-modal="true" aria-label="مدیریت فرصت‌ها" style={{position:"fixed",inset:0,zIndex:1450,background:"rgba(15,23,42,.58)",display:"grid",placeItems:"center",padding:18}}>
    <section style={{width:"min(1120px,96vw)",height:"min(760px,92vh)",background:"white",borderRadius:18,boxShadow:"0 24px 70px rgba(15,23,42,.35)",display:"grid",gridTemplateRows:"auto 1fr",overflow:"hidden"}}>
      <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,padding:"16px 18px",borderBottom:"1px solid #e2e8f0"}}>
        <div><small style={{color:"#64748b"}}>فرآیند انسانی و قابل Audit</small><h2 style={{margin:"3px 0 0"}}>مدیریت فرصت‌ها و پرونده‌های منتخب</h2></div>
        <button type="button" onClick={onClose} aria-label="بستن" style={{border:0,borderRadius:10,width:38,height:38,fontSize:24,cursor:"pointer"}}>×</button>
      </header>
      <div style={{display:"grid",gridTemplateColumns:"minmax(280px,.8fr) minmax(420px,1.4fr)",minHeight:0}}>
        <aside style={{borderInlineEnd:"1px solid #e2e8f0",padding:14,overflow:"auto",background:"#f8fafc"}}>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی عنوان، کارفرما یا مرحله" style={{width:"100%",boxSizing:"border-box",padding:"10px 12px",border:"1px solid #cbd5e1",borderRadius:10,marginBottom:10}} />
          {loading ? <p>در حال دریافت پرونده‌های واقعی...</p> : filtered.length ? filtered.map((item) => <button key={item.id} type="button" onClick={() => choose(item)} style={{width:"100%",textAlign:"right",padding:12,marginBottom:8,border:item.id===selectedId?"2px solid #0f766e":"1px solid #dbe3ec",borderRadius:12,background:"white",cursor:"pointer"}}>
            <b style={{display:"block",marginBottom:5}}>{item.notice_title}</b>
            <span style={{display:"block",fontSize:12,color:"#475569"}}>{item.notice_employer_name || "کارفرما نامشخص"} · {item.notice_type_label}</span>
            <span style={{display:"inline-block",marginTop:7,fontSize:11,padding:"3px 7px",borderRadius:999,background:terminalStages.has(item.stage)?"#f1f5f9":"#ecfdf5",color:terminalStages.has(item.stage)?"#475569":"#047857"}}>{item.stage_label}</span>
          </button>) : <p>پرونده‌ای مطابق جست‌وجو وجود ندارد.</p>}
        </aside>
        <main style={{padding:18,overflow:"auto"}}>
          <div style={{padding:"10px 12px",borderRadius:10,background:"#fff7ed",border:"1px solid #fed7aa",color:"#9a3412",fontSize:13,marginBottom:14}}>هیچ مرحله، نتیجه یا قراردادی خودکار نهایی نمی‌شود. هر تغییر فقط با ذخیره صریح کاربر انجام می‌شود.</div>
          {message && <div role="status" style={{padding:"9px 11px",borderRadius:9,background:message.includes("موفقیت")?"#ecfdf5":"#fff1f2",color:message.includes("موفقیت")?"#047857":"#9f1239",marginBottom:12}}>{message}</div>}
          {!selected || !draft ? <p>یک پرونده را انتخاب کنید.</p> : <form onSubmit={save} style={{display:"grid",gap:13}}>
            <div><small style={{color:"#64748b"}}>{selected.notice_type_label}</small><h3 style={{margin:"4px 0"}}>{selected.notice_title}</h3><p style={{margin:0,color:"#475569"}}>{selected.notice_employer_name || "کارفرما نامشخص"}</p></div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:12}}>
              <label>مرحله<select value={draft.stage} onChange={(event) => setDraft({...draft,stage:event.target.value})} style={fieldStyle}>{availableStages.map((stage) => <option key={stage} value={stage}>{stageLabels[stage] || stage}</option>)}</select></label>
              <label>پیشرفت درصد<input type="number" min={0} max={100} value={draft.progress} onChange={(event) => setDraft({...draft,progress:Number(event.target.value)})} style={fieldStyle} /></label>
            </div>
            <label>اقدام بعدی<input value={draft.next_action} onChange={(event) => setDraft({...draft,next_action:event.target.value})} maxLength={500} style={fieldStyle} /></label>
            <label>موعد اقدام بعدی<input type="datetime-local" value={draft.next_action_due} onChange={(event) => setDraft({...draft,next_action_due:event.target.value})} style={fieldStyle} /><small style={{color:"#64748b"}}>موعد فعلی: {dateLabel(selected.next_action_due)}</small></label>
            <label>دلیل تصمیم<textarea value={draft.decision_reason} onChange={(event) => setDraft({...draft,decision_reason:event.target.value})} maxLength={500} rows={4} required={draft.stage === "do_not_participate"} style={{...fieldStyle,resize:"vertical"}} /></label>
            <dl style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:8,margin:0}}><div><dt style={{fontSize:11,color:"#64748b"}}>مسئول</dt><dd style={{margin:0}}>{selected.responsible_username || "تعیین نشده"}</dd></div><div><dt style={{fontSize:11,color:"#64748b"}}>اسناد ارسالی</dt><dd style={{margin:0}}>{selected.submission_document_count}</dd></div><div><dt style={{fontSize:11,color:"#64748b"}}>مرحله فعلی</dt><dd style={{margin:0}}>{selected.stage_label}</dd></div></dl>
            <div style={{display:"flex",justifyContent:"space-between",gap:10,flexWrap:"wrap",marginTop:4}}><button type="button" onClick={() => void load()} style={{padding:"9px 13px",border:"1px solid #cbd5e1",borderRadius:9,background:"white",cursor:"pointer"}}>بازخوانی</button><button type="submit" disabled={saving} style={{padding:"10px 16px",border:0,borderRadius:9,background:"#0f766e",color:"white",fontWeight:700,cursor:"pointer"}}>{saving ? "در حال ذخیره..." : "ذخیره تغییرات پرونده"}</button></div>
          </form>}
        </main>
      </div>
    </section>
  </div>;
}
