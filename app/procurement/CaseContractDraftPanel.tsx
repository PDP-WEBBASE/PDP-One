"use client";

import { useEffect, useMemo, useState } from "react";

type CaseRecord = { id:string; notice:string; stage:string; stage_label:string; updated_at:string };
type NoticeRecord = { id:string; title:string; employer_name:string; estimated_amount_rials:string|null };
type ContractRecord = { id:string; code:string; title:string; employer:string; field:string; value_rials:string|null; due_date:string|null; status:string };
type Preview = { eligible:boolean; case_id:string; case_stage_label:string; proposal:ContractRecord; existing_contract:ContractRecord|null; requires_explicit_confirmation:boolean; creates_financial_records:boolean };
type Collection<T> = T[] | { results?:T[]; next?:string|null };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const P = `${API_BASE}/procurement`;
const fieldStyle = {width:"100%",boxSizing:"border-box",padding:9,border:"1px solid #cbd5e1",borderRadius:9,font:"inherit"} as const;

function pathOnly(value:string){ const url=new URL(value,window.location.origin); return `${url.pathname}${url.search}`; }
async function fetchAll<T>(path:string){ const out:T[]=[]; let next:string|null=path; let pages=0; while(next&&pages<20){ const response=await fetch(next,{credentials:"include",headers:{Accept:"application/json"}}); if(!response.ok) throw new Error("دریافت اطلاعات پرونده‌ها انجام نشد."); const payload=await response.json() as Collection<T>; if(Array.isArray(payload)){out.push(...payload);next=null;}else{out.push(...(payload.results||[]));next=payload.next?pathOnly(payload.next):null;} pages+=1;} return out; }
async function csrf(){ const response=await fetch(`${API_BASE}/auth/session/`,{credentials:"include",headers:{Accept:"application/json"}}); if(!response.ok) throw new Error("نشست کاربری در دسترس نیست."); return String(((await response.json()) as {csrf_token?:string}).csrf_token||""); }

export default function CaseContractDraftPanel({onClose}:{onClose:()=>void}){
  const [cases,setCases]=useState<CaseRecord[]>([]);
  const [notices,setNotices]=useState<NoticeRecord[]>([]);
  const [selectedId,setSelectedId]=useState("");
  const [preview,setPreview]=useState<Preview|null>(null);
  const [form,setForm]=useState({title:"",employer:"",field:"",value_rials:"",due_date:""});
  const [loading,setLoading]=useState(true);
  const [working,setWorking]=useState(false);
  const [message,setMessage]=useState("");

  useEffect(()=>{ let active=true; Promise.all([
    fetchAll<CaseRecord>(`${P}/cases/?stage=won&ordering=-updated_at`),
    fetchAll<NoticeRecord>(`${P}/notices/?ordering=-last_seen_at`),
  ]).then(([loadedCases,loadedNotices])=>{ if(!active)return; const wonCases=loadedCases.filter(item=>item.stage==="won");setCases(wonCases);setNotices(loadedNotices);if(wonCases[0])setSelectedId(wonCases[0].id); }).catch(error=>{if(active)setMessage(error instanceof Error?error.message:"دریافت اطلاعات انجام نشد.");}).finally(()=>{if(active)setLoading(false);}); return()=>{active=false;}; },[]);

  const noticeMap=useMemo(()=>new Map(notices.map(item=>[item.id,item])),[notices]);
  const selected=cases.find(item=>item.id===selectedId)||null;

  useEffect(()=>{ if(!selectedId)return; let active=true; fetch(`${P}/cases/${selectedId}/contract-preview/`,{credentials:"include",headers:{Accept:"application/json"}}).then(async response=>{const payload=await response.json() as Preview&{detail?:string};if(!response.ok)throw new Error(payload.detail||"پیش‌نمایش قرارداد دریافت نشد.");if(!active)return;setPreview(payload);const p=payload.existing_contract||payload.proposal;setForm({title:p.title||"",employer:p.employer||"",field:p.field||"",value_rials:p.value_rials||"",due_date:p.due_date||""});}).catch(error=>{if(active)setMessage(error instanceof Error?error.message:"پیش‌نمایش قرارداد دریافت نشد.");}); return()=>{active=false;}; },[selectedId]);

  async function createDraft(){ if(!selected||!preview)return; setWorking(true);setMessage("");try{const token=await csrf();const response=await fetch(`${P}/cases/${selected.id}/contract-draft/`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json","X-CSRFToken":token,Accept:"application/json"},body:JSON.stringify({confirmed:true,title:form.title.trim(),employer:form.employer.trim(),field:form.field.trim(),value_rials:form.value_rials||null,due_date:form.due_date||null})});const payload=await response.json() as {detail?:string;created?:boolean;contract?:ContractRecord};if(!response.ok)throw new Error(payload.detail||"ایجاد پیش‌نویس قرارداد انجام نشد.");setPreview(current=>current?{...current,existing_contract:payload.contract||current.existing_contract}:current);setMessage(payload.created?"قرارداد فقط با وضعیت پیش‌نویس ایجاد شد و نیازمند بازبینی انسانی است.":"پیش‌نویس قرارداد از قبل وجود داشت و دوباره ایجاد نشد.");}catch(error){setMessage(error instanceof Error?error.message:"ایجاد پیش‌نویس قرارداد انجام نشد.");}finally{setWorking(false);}}

  return <div dir="rtl" role="dialog" aria-modal="true" aria-label="تبدیل پرونده برنده به قرارداد پیش‌نویس" style={{position:"fixed",inset:0,zIndex:1540,background:"rgba(15,23,42,.62)",display:"grid",placeItems:"center",padding:16}}><section style={{width:"min(1050px,96vw)",height:"min(720px,92vh)",background:"white",borderRadius:18,display:"grid",gridTemplateRows:"auto 1fr",overflow:"hidden"}}>
    <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"15px 18px",borderBottom:"1px solid #e2e8f0"}}><div><small style={{color:"#64748b"}}>فقط پرونده برنده، فقط قرارداد Draft</small><h2 style={{margin:"3px 0 0"}}>ایجاد پیش‌نویس قرارداد</h2></div><button type="button" onClick={onClose} aria-label="بستن" style={{border:0,fontSize:24}}>×</button></header>
    <div style={{display:"grid",gridTemplateColumns:"minmax(280px,.8fr) minmax(420px,1.3fr)",minHeight:0}}><aside style={{padding:13,overflow:"auto",background:"#f8fafc",borderInlineEnd:"1px solid #e2e8f0"}}>{loading?<p>در حال دریافت پرونده‌های برنده...</p>:cases.length?cases.map(item=>{const notice=noticeMap.get(item.notice);return <button key={item.id} type="button" onClick={()=>{setPreview(null);setSelectedId(item.id);setMessage("");}} style={{width:"100%",textAlign:"right",padding:11,marginBottom:7,background:"white",border:item.id===selectedId?"2px solid #0f766e":"1px solid #dbe3ec",borderRadius:10}}><b style={{display:"block"}}>{notice?.title||"عنوان ثبت نشده"}</b><small>{notice?.employer_name||"کارفرما نامشخص"} · {item.stage_label}</small></button>}):<p>پرونده برنده‌ای برای تبدیل وجود ندارد.</p>}</aside>
    <main style={{padding:18,overflow:"auto"}}><div style={{padding:10,background:"#fff7ed",border:"1px solid #fed7aa",borderRadius:9,color:"#9a3412",marginBottom:12}}>این عملیات قرارداد فعال یا سند مالی ایجاد نمی‌کند. نتیجه فقط پیش‌نویس و نیازمند بازبینی انسانی است.</div>{message&&<div role="status" style={{padding:9,borderRadius:9,background:message.includes("انجام نشد")?"#fff1f2":"#ecfdf5",marginBottom:12}}>{message}</div>}
      {!selected||!preview?<p>یک پرونده برنده را انتخاب کنید.</p>:preview.existing_contract?<div><h3>پیش‌نویس قرارداد موجود است</h3><p>کد: <b>{preview.existing_contract.code}</b></p><p>وضعیت: <b>{preview.existing_contract.status}</b></p><p>برای جلوگیری از رکورد تکراری، قرارداد دیگری ساخته نمی‌شود.</p></div>:<div style={{display:"grid",gap:11}}><label>عنوان قرارداد<input value={form.title} onChange={e=>setForm({...form,title:e.target.value})} style={fieldStyle}/></label><label>کارفرما<input value={form.employer} onChange={e=>setForm({...form,employer:e.target.value})} style={fieldStyle}/></label><label>رشته/حوزه<input value={form.field} onChange={e=>setForm({...form,field:e.target.value})} style={fieldStyle}/></label><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}><label>مبلغ برآوردی ریال<input type="number" min="0" value={form.value_rials} onChange={e=>setForm({...form,value_rials:e.target.value})} style={fieldStyle}/></label><label>تاریخ پایان پیشنهادی<input type="date" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})} style={fieldStyle}/></label></div><p style={{margin:0}}>کد پیشنهادی: <b>{preview.proposal.code}</b></p><button type="button" disabled={working||!preview.eligible} onClick={()=>void createDraft()} style={{padding:"11px 15px",border:0,borderRadius:9,background:"#0f766e",color:"white",fontWeight:700}}>{working?"در حال ایجاد...":"تأیید و ایجاد قرارداد پیش‌نویس"}</button></div>}
    </main></div>
  </section></div>;
}
