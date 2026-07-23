"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import styles from "./workspace-v4.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type NoticeStage = "" | "selected" | "preparing" | "submitted" | "results";
type DirectStage = "new" | "reviewing" | "selected" | "preparing" | "submitted" | "won" | "lost";
type Importance = "low" | "medium" | "high" | "very_high";

type Notice = {
  id: string;
  referenceCode: string | null;
  kind: "tender" | "inquiry";
  title: string;
  employer: string;
  province: string;
  source: string;
  sourceUrl: string;
  publishedDate: string;
  deadline: string | null;
  importance: Importance;
  recommended: boolean;
  stage: NoticeStage;
  result: string;
  score: number | null;
  responsible: string;
  nextAction: string;
  progress: number;
  documents: string[];
};

type DirectReferral = {
  id: string;
  referenceCode: string | null;
  title: string;
  employer: string;
  opportunityType: string;
  domain: string;
  province: string;
  city: string;
  description: string;
  estimatedValue: string;
  probability: number | null;
  importance: Importance;
  responsible: string;
  targetDeadline: string | null;
  contactName: string;
  contactPhone: string;
  contactEmail: string;
  confidentiality: string;
  stage: DirectStage;
  documents: string[];
};

type SelectedRecord = {
  title: string;
  code: string | null;
  employer: string;
  status: string;
  documents: string[];
  showCode: boolean;
};

const fa = new Intl.NumberFormat("fa-IR");
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
const importanceLabels: Record<Importance, string> = {
  low: "کم",
  medium: "متوسط",
  high: "زیاد",
  very_high: "بسیار زیاد",
};

const initialNotices: Notice[] = [
  { id:"T1", referenceCode:"TND-10000", kind:"tender", title:"خدمات مشاوره طراحی و نظارت مجموعه اداری", employer:"شرکت توسعه عمران", province:"تهران", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/tenders/nid10950416", publishedDate:"۱۴۰۵/۰۵/۰۱", deadline:"2026-07-25T16:00:00+03:30", importance:"very_high", recommended:true, stage:"selected", result:"", score:91, responsible:"محمد ملکی", nextAction:"تقسیم کار تهیه پیشنهاد", progress:35, documents:["شرح خدمات.pdf"] },
  { id:"T2", referenceCode:"TND-10001", kind:"tender", title:"مطالعات طرح جامع و برنامه‌ریزی فضایی", employer:"اداره کل راه و شهرسازی", province:"فارس", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/tenders/-%21/page-1", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-30T14:00:00+03:30", importance:"high", recommended:true, stage:"preparing", result:"", score:95, responsible:"کارشناس مناقصات", nextAction:"تهیه ساختار شکست خدمات", progress:62, documents:["رزومه تیم.pdf","روش انجام کار.docx"] },
  { id:"T3", referenceCode:null, kind:"tender", title:"طراحی تأسیسات بیمارستان", employer:"دانشگاه علوم پزشکی", province:"البرز", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/tenders/-%21/page-1", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-27T12:00:00+03:30", importance:"medium", recommended:false, stage:"", result:"", score:null, responsible:"", nextAction:"بررسی اولیه", progress:0, documents:[] },
  { id:"T4", referenceCode:null, kind:"tender", title:"مطالعات بازآفرینی بافت شهری", employer:"شهرداری نمونه", province:"کرمان", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/tenders/-%21/page-1", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-08-02T15:00:00+03:30", importance:"high", recommended:true, stage:"", result:"", score:87, responsible:"", nextAction:"تصمیم مدیر", progress:0, documents:[] },
  { id:"I1", referenceCode:"INQ-10000", kind:"inquiry", title:"استعلام خدمات نقشه‌برداری", employer:"شهرداری منطقه", province:"تهران", source:"پارس‌نماد داده", sourceUrl:"https://www.parsnamaddata.com/inquiries/page/1", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-23T13:00:00+03:30", importance:"high", recommended:true, stage:"selected", result:"", score:88, responsible:"کارشناس مناقصات", nextAction:"دریافت قیمت و تأیید مدیر", progress:70, documents:[] },
  { id:"I2", referenceCode:"INQ-10001", kind:"inquiry", title:"استعلام گزارش توجیهی و امکان‌سنجی", employer:"منطقه ویژه اقتصادی", province:"بوشهر", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/inquiries/-%21/page-1", publishedDate:"۱۴۰۵/۰۵/۰۱", deadline:"2026-07-26T15:00:00+03:30", importance:"very_high", recommended:true, stage:"preparing", result:"", score:86, responsible:"واحد مطالعات", nextAction:"جلسه با کارشناس مالی", progress:48, documents:["پیش‌نویس پیشنهاد.pdf"] },
  { id:"I3", referenceCode:null, kind:"inquiry", title:"استعلام طراحی روشنایی محوطه صنعتی", employer:"شرکت تولیدی نمونه", province:"قزوین", source:"پارس‌نماد داده", sourceUrl:"https://www.parsnamaddata.com/inquiries/page/1", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-07-24T10:00:00+03:30", importance:"medium", recommended:false, stage:"", result:"", score:null, responsible:"", nextAction:"دریافت پیوست فنی", progress:0, documents:[] },
  { id:"I4", referenceCode:null, kind:"inquiry", title:"استعلام مطالعات ترافیکی", employer:"سازمان حمل‌ونقل", province:"تهران", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net/inquiries/-%21/page-1", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-07-29T12:00:00+03:30", importance:"high", recommended:true, stage:"", result:"", score:84, responsible:"", nextAction:"تصمیم مدیر", progress:0, documents:[] },
];

const initialDirect: DirectReferral[] = [
  { id:"D1", referenceCode:null, title:"رایزنی طرح توسعه پردیس اداری", employer:"گروه سرمایه‌گذاری پارس", opportunityType:"رایزنی با کارفرما", domain:"معماری اداری", province:"تهران", city:"تهران", description:"طراحی و توسعه پردیس اداری", estimatedValue:"", probability:40, importance:"high", responsible:"محمد ملکی", targetDeadline:null, contactName:"نماینده کارفرما", contactPhone:"", contactEmail:"", confidentiality:"داخلی", stage:"new", documents:[] },
  { id:"D2", referenceCode:null, title:"مطالعات امکان‌سنجی نیروگاه خورشیدی", employer:"شرکت انرژی نو", opportunityType:"معرفی مستقیم", domain:"امکان‌سنجی", province:"یزد", city:"", description:"مطالعات فنی و اقتصادی", estimatedValue:"", probability:55, importance:"medium", responsible:"توسعه کسب‌وکار", targetDeadline:"2026-08-10T12:00:00+03:30", contactName:"", contactPhone:"", contactEmail:"", confidentiality:"داخلی", stage:"reviewing", documents:[] },
  { id:"D3", referenceCode:"DIR-10000", title:"دعوت محدود طراحی مجموعه درمانی", employer:"بنیاد توسعه سلامت", opportunityType:"دعوت محدود", domain:"معماری درمانی", province:"تهران", city:"", description:"طراحی معماری و تأسیسات", estimatedValue:"78000000000", probability:80, importance:"very_high", responsible:"مدیر فنی", targetDeadline:"2026-07-22T12:00:00+03:30", contactName:"دبیرخانه بنیاد", contactPhone:"", contactEmail:"", confidentiality:"داخلی", stage:"submitted", documents:["پیشنهاد معماری.pdf","رسید ایمیل.pdf"] },
];

function urgency(value: string | null) {
  if (!value) return { tone: "unknown", label: "تاریخ نامشخص", remaining: "نامشخص" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone:"critical", label:"مهلت گذشته", remaining:`${fa.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone:"critical", label:"فوریت بحرانی", remaining:`${fa.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone:"high", label:"فوریت زیاد", remaining:`${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  return { tone:"normal", label:"عادی", remaining:`${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
}

function viewLabel(tab: Tab, view: WorkflowView) {
  if (view !== "all") return standardViews.find(([id]) => id === view)?.[1] || view;
  if (tab === "tenders") return "کل مناقصات";
  if (tab === "inquiries") return "کل استعلامات";
  return "کل ارجاعات مستقیم";
}

function noticeMatches(item: Notice, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return item.recommended && !item.stage;
  if (view === "selected") return item.stage === "selected" || item.stage === "preparing";
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "results";
}

function directMatches(item: DirectReferral, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return item.stage === "reviewing";
  if (view === "selected") return item.stage === "selected" || item.stage === "preparing";
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "won" || item.stage === "lost";
}

function nextCode(items: { referenceCode: string | null }[], prefix: string) {
  const max = Math.max(9999, ...items.map((item) => item.referenceCode).filter((code): code is string => Boolean(code?.startsWith(`${prefix}-`))).map((code) => Number(code.split("-")[1]) || 9999));
  return `${prefix}-${max + 1}`;
}

export default function ProcurementWorkspaceV9() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [notices, setNotices] = useState(initialNotices);
  const [direct, setDirect] = useState(initialDirect);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [provinceFilter, setProvinceFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [urgencyFilter, setUrgencyFilter] = useState("");
  const [directTypeFilter, setDirectTypeFilter] = useState("");
  const [message, setMessage] = useState("");
  const [showDirectModal, setShowDirectModal] = useState(false);
  const [selected, setSelected] = useState<SelectedRecord | null>(null);
  const [schedule, setSchedule] = useState({ enabled:true, cadence:"daily", dailyTime:"17:00", intervalHours:1, lookbackDays:7 });

  const showNoticeCode = noticeView === "selected" || noticeView === "submitted" || noticeView === "results";
  const showDirectCode = directView === "selected" || directView === "submitted" || directView === "results";
  const noticeViews: [WorkflowView, string][] = [["all", viewLabel(tab, "all")], ...standardViews];
  const directViews: [WorkflowView, string][] = [["all", viewLabel("direct", "all")], ...standardViews];

  const filteredNotices = useMemo(() => notices.filter((item) => {
    const currentUrgency = urgency(item.deadline);
    return (tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry")
      && noticeMatches(item, noticeView)
      && (!search || `${item.referenceCode || ""} ${item.title} ${item.employer} ${item.province}`.includes(search))
      && (!sourceFilter || item.source === sourceFilter)
      && (!provinceFilter || item.province === provinceFilter)
      && (!importanceFilter || item.importance === importanceFilter)
      && (!urgencyFilter || currentUrgency.tone === urgencyFilter);
  }), [notices, tab, noticeView, search, sourceFilter, provinceFilter, importanceFilter, urgencyFilter]);

  const filteredDirect = useMemo(() => direct.filter((item) => directMatches(item, directView)
    && (!search || `${item.referenceCode || ""} ${item.title} ${item.employer} ${item.domain}`.includes(search))
    && (!provinceFilter || item.province === provinceFilter)
    && (!importanceFilter || item.importance === importanceFilter)
    && (!directTypeFilter || item.opportunityType === directTypeFilter)), [direct, directView, search, provinceFilter, importanceFilter, directTypeFilter]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 3200);
  }

  function resetFilters() {
    setSearch("");
    setSourceFilter("");
    setProvinceFilter("");
    setImportanceFilter("");
    setUrgencyFilter("");
    setDirectTypeFilter("");
  }

  function updateNotice(id: string, change: Partial<Notice>) {
    setNotices((items) => items.map((item) => item.id === id ? { ...item, ...change } : item));
  }

  function updateDirect(id: string, change: Partial<DirectReferral>) {
    setDirect((items) => items.map((item) => item.id === id ? { ...item, ...change } : item));
  }

  function selectNotice(id: string) {
    setNotices((items) => {
      const item = items.find((candidate) => candidate.id === id);
      if (!item) return items;
      const prefix = item.kind === "tender" ? "TND" : "INQ";
      const code = item.referenceCode || nextCode(items.filter((candidate) => candidate.kind === item.kind), prefix);
      notify(`پرونده منتخب شد و کد ${code} دریافت کرد.`);
      return items.map((candidate) => candidate.id === id ? { ...candidate, stage:"selected", referenceCode:code } : candidate);
    });
  }

  function selectDirect(id: string) {
    setDirect((items) => {
      const item = items.find((candidate) => candidate.id === id);
      if (!item) return items;
      const code = item.referenceCode || nextCode(items, "DIR");
      notify(`ارجاع منتخب شد و کد ${code} دریافت کرد.`);
      return items.map((candidate) => candidate.id === id ? { ...candidate, stage:"selected", referenceCode:code } : candidate);
    });
  }

  function uploadNotice(id: string, event: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(event.target.files || []).map((file) => file.name);
    setNotices((items) => items.map((item) => item.id === id ? { ...item, documents:[...item.documents, ...names] } : item));
    notify(`${fa.format(names.length)} سند به پرونده افزوده شد.`);
  }

  function uploadDirect(id: string, event: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(event.target.files || []).map((file) => file.name);
    setDirect((items) => items.map((item) => item.id === id ? { ...item, documents:[...item.documents, ...names] } : item));
    notify(`${fa.format(names.length)} سند به پرونده افزوده شد.`);
  }

  function registerDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form.entries());
    if (!Object.values(values).some((value) => String(value).trim())) {
      notify("حداقل یک اطلاعات معنادار وارد کنید.");
      return;
    }
    const item: DirectReferral = {
      id:`D-${Date.now()}`,
      referenceCode:null,
      title:String(form.get("title") || "").trim(),
      employer:String(form.get("employer") || "").trim(),
      opportunityType:String(form.get("opportunityType") || "نیازمند تعیین"),
      domain:String(form.get("domain") || "").trim(),
      province:String(form.get("province") || "").trim(),
      city:String(form.get("city") || "").trim(),
      description:String(form.get("description") || "").trim(),
      estimatedValue:String(form.get("estimatedValue") || "").trim(),
      probability:form.get("probability") ? Number(form.get("probability")) : null,
      importance:String(form.get("importance") || "medium") as Importance,
      responsible:String(form.get("responsible") || "").trim(),
      targetDeadline:String(form.get("targetDeadline") || "") || null,
      contactName:String(form.get("contactName") || "").trim(),
      contactPhone:String(form.get("contactPhone") || "").trim(),
      contactEmail:String(form.get("contactEmail") || "").trim(),
      confidentiality:String(form.get("confidentiality") || "داخلی"),
      stage:"new",
      documents:[],
    };
    setDirect((items) => [item, ...items]);
    event.currentTarget.reset();
    setDirectView("all");
    setShowDirectModal(false);
    notify("ارجاع در «کل ارجاعات مستقیم» ثبت شد؛ کد دائمی پس از انتخاب ساخته می‌شود.");
  }

  function openNotice(item: Notice, status: string, showCode: boolean) {
    setSelected({ title:item.title, code:item.referenceCode, employer:item.employer, status, documents:item.documents, showCode });
  }

  function openDirect(item: DirectReferral, status: string, showCode: boolean) {
    setSelected({ title:item.title || "ارجاع بدون عنوان", code:item.referenceCode, employer:item.employer || "کارفرما ثبت نشده", status, documents:item.documents, showCode });
  }

  function noticeActions(item: Notice) {
    if (noticeView === "all") return <>
      {!item.recommended && !item.stage && <button className={styles.primaryButton} onClick={() => updateNotice(item.id, { recommended:true })}>افزودن به پیشنهادی</button>}
      <button className={styles.secondaryButton} onClick={() => openNotice(item, item.stage || viewLabel(tab, "all"), false)}>مشاهده</button>
    </>;
    if (noticeView === "recommended") return <><button className={styles.primaryButton} onClick={() => selectNotice(item.id)}>انتخاب و ساخت کد</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { recommended:false })}>حذف</button></>;
    if (noticeView === "selected") return <><label className={styles.fileButton}>بارگذاری اسناد<input type="file" multiple onChange={(event) => uploadNotice(item.id, event)} /></label><button className={styles.primaryButton} onClick={() => updateNotice(item.id, { stage:"submitted", progress:100 })}>ارسال شد</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { stage:"", recommended:true })}>حذف</button></>;
    if (noticeView === "submitted") return <><button className={styles.primaryButton} onClick={() => updateNotice(item.id, { stage:"results", result:"برنده" })}>ثبت نتیجه</button><button className={styles.secondaryButton} onClick={() => openNotice(item, "ارسال‌شده", true)}>اسناد</button></>;
    return <button className={styles.secondaryButton} onClick={() => openNotice(item, item.result || "نتایج", true)}>مشاهده پرونده</button>;
  }

  function directActions(item: DirectReferral) {
    if (directView === "all") return <>{item.stage === "new" ? <button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage:"reviewing" })}>افزودن به پیشنهادی</button> : <button className={styles.statusButton} disabled>{item.stage === "reviewing" ? "پیشنهادی" : item.stage === "selected" ? "منتخب" : item.stage === "submitted" ? "ارسال‌شده" : "نتیجه"}</button>}<button className={styles.secondaryButton} onClick={() => openDirect(item, item.stage, false)}>مشاهده</button></>;
    if (directView === "recommended") return <><button className={styles.primaryButton} onClick={() => selectDirect(item.id)}>انتخاب و ساخت کد</button><button className={styles.dangerButton} onClick={() => updateDirect(item.id, { stage:"new" })}>حذف</button></>;
    if (directView === "selected") return <><label className={styles.fileButton}>بارگذاری اسناد<input type="file" multiple onChange={(event) => uploadDirect(item.id, event)} /></label><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage:"submitted" })}>ارسال شد</button><button className={styles.dangerButton} onClick={() => updateDirect(item.id, { stage:"reviewing" })}>حذف</button></>;
    if (directView === "submitted") return <><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage:"won" })}>ثبت موفق</button><button className={styles.secondaryButton} onClick={() => openDirect(item, "ارسال‌شده", true)}>اسناد</button></>;
    return <button className={styles.secondaryButton} onClick={() => openDirect(item, item.stage === "won" ? "موفق" : "ناموفق", true)}>مشاهده پرونده</button>;
  }

  const filterBoxStyle = { display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:10, padding:12, border:"1px solid rgba(15,23,42,.12)", borderRadius:14, background:"#f8fafc", marginBottom:14 } as const;
  const filterInputStyle = { width:"100%", minHeight:40, border:"1px solid rgba(15,23,42,.16)", borderRadius:10, padding:"8px 10px", background:"white" } as const;

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}><div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1><p>فوریت از مهلت زمانی محاسبه می‌شود؛ اهمیت نشان‌دهنده ارزش و تناسب فرصت برای شرکت است.</p></div><Link href="/">بازگشت به سامانه</Link></header>
    <div className={styles.banner}><b>Preview تعاملی</b><span>کد دائمی فقط از مرحله منتخب به بعد نمایش داده می‌شود.</span></div>
    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); resetFilters(); setNoticeView("all"); setDirectView("all"); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section><div className={styles.kpis}><article className={styles.kpi}><span>فراخوان امروز</span><b>۴</b><small>۲ مناقصه · ۲ استعلام</small></article><article className={styles.kpi}><span>اهمیت زیاد و بسیار زیاد</span><b>۵</b><small>نیازمند بررسی مدیر</small></article><article className={styles.kpi}><span>فراخوان دیروز</span><b>۳</b><small>۲ مناقصه · ۱ استعلام</small></article><article className={styles.kpi}><span>پیشنهادی دیروز</span><b>۳</b><small>نیازمند تصمیم</small></article></div><div className={styles.dashboardGrid}><article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>۳ اقدام عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>۴ پرونده نزدیک مهلت</span></div></article><article className={styles.panel}><h2>بازیابی سریع با کد</h2><p>بازیابی با کد از مرحله منتخب به بعد فعال است؛ مانند <b>TND-10001</b>، <b>INQ-10000</b> یا <b>DIR-10000</b>.</p></article></div></section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <div className={styles.views}>{noticeViews.map(([id, label]) => <button key={id} className={noticeView === id ? styles.active : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div>
      <div style={filterBoxStyle} aria-label="جست‌وجو و فیلتر فراخوان‌ها">
        <label>جست‌وجوی متن<input style={filterInputStyle} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، استان یا کد" /></label>
        <label>منبع<select style={filterInputStyle} value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">همه منابع</option>{[...new Set(notices.map((item) => item.source))].map((source) => <option key={source}>{source}</option>)}</select></label>
        <label>استان<select style={filterInputStyle} value={provinceFilter} onChange={(event) => setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(notices.map((item) => item.province))].map((province) => <option key={province}>{province}</option>)}</select></label>
        <label>اهمیت<select style={filterInputStyle} value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>فوریت<select style={filterInputStyle} value={urgencyFilter} onChange={(event) => setUrgencyFilter(event.target.value)}><option value="">همه وضعیت‌ها</option><option value="critical">بحرانی یا گذشته</option><option value="high">زیاد</option><option value="normal">عادی</option><option value="unknown">نامشخص</option></select></label>
        <div style={{display:"flex",alignItems:"end",gap:8}}><button className={styles.secondaryButton} onClick={resetFilters}>پاک‌کردن فیلترها</button><b>{fa.format(filteredNotices.length)} رکورد</b></div>
      </div>
      <div className={styles.recordList}>{filteredNotices.map((item, index) => { const itemUrgency = urgency(item.deadline); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small><b>ردیف {fa.format(index + 1)}</b>{showNoticeCode && item.referenceCode && <> · <span className={styles.codeBadge}>{item.referenceCode}</span></>} · {item.source} · انتشار {item.publishedDate}</small><div style={{display:"flex",gap:7,flexWrap:"wrap"}}><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}>{itemUrgency.label}</span><span className={styles.codeBadge}>اهمیت {importanceLabels[item.importance]}</span></div></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{itemUrgency.remaining}</span><span>امتیاز تحلیل: {item.score ?? "تحلیل نشده"}</span>{item.documents.length > 0 && <span>{fa.format(item.documents.length)} سند</span>}<a href={item.sourceUrl} target="_blank" rel="noreferrer">مشاهده آگهی در سایت منبع ↗</a></div></div><div className={styles.decision}><span className={styles.stage}>{item.result || item.stage || (item.recommended ? "پیشنهادی" : viewLabel(tab, "all"))}</span><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div></dl><div className={styles.actions}>{noticeActions(item)}</div></div></article>; })}</div>
    </section>}

    {tab === "direct" && <section><div style={{display:"flex",justifyContent:"flex-end",marginBottom:14}}><button className={styles.primaryButton} onClick={() => setShowDirectModal(true)}>ثبت ارجاع مستقیم جدید</button></div><div className={styles.views}>{directViews.map(([id,label]) => <button key={id} className={directView === id ? styles.active : ""} onClick={() => setDirectView(id)}>{label}</button>)}</div><div style={filterBoxStyle}><label>جست‌وجوی متن<input style={filterInputStyle} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، حوزه یا کد" /></label><label>نوع ارجاع<select style={filterInputStyle} value={directTypeFilter} onChange={(event) => setDirectTypeFilter(event.target.value)}><option value="">همه انواع</option>{[...new Set(direct.map((item) => item.opportunityType))].map((type) => <option key={type}>{type}</option>)}</select></label><label>استان<select style={filterInputStyle} value={provinceFilter} onChange={(event) => setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(direct.map((item) => item.province))].map((province) => <option key={province}>{province}</option>)}</select></label><label>اهمیت<select style={filterInputStyle} value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><div style={{display:"flex",alignItems:"end",gap:8}}><button className={styles.secondaryButton} onClick={resetFilters}>پاک‌کردن فیلترها</button><b>{fa.format(filteredDirect.length)} رکورد</b></div></div><div className={styles.recordList}>{filteredDirect.map((item,index) => { const itemUrgency=urgency(item.targetDeadline); const facts=[item.domain,item.province,item.city,item.probability!=null?`احتمال تبدیل: ${fa.format(item.probability)}٪`:"",item.documents.length?`${fa.format(item.documents.length)} سند`:""].filter(Boolean); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small><b>ردیف {fa.format(index+1)}</b>{showDirectCode&&item.referenceCode&&<> · <span className={styles.codeBadge}>{item.referenceCode}</span></>} · {item.opportunityType}</small><div style={{display:"flex",gap:7,flexWrap:"wrap"}}><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}>{itemUrgency.label}</span><span className={styles.codeBadge}>اهمیت {importanceLabels[item.importance]}</span></div></div><h3>{item.title||"ارجاع بدون عنوان"}</h3>{item.employer&&<p>{item.employer}</p>}<div className={styles.facts}>{facts.map((fact)=><span key={fact}>{fact}</span>)}</div></div><div className={styles.decision}><span className={styles.stage}>{item.stage==="new"?viewLabel("direct","all"):item.stage==="reviewing"?"پیشنهادی":item.stage==="selected"||item.stage==="preparing"?"منتخب":item.stage==="submitted"?"ارسال‌شده":item.stage==="won"?"موفق":"ناموفق"}</span><dl>{item.responsible&&<div><dt>مسئول</dt><dd>{item.responsible}</dd></div>}{item.contactName&&<div><dt>رابط</dt><dd>{item.contactName}</dd></div>}</dl><div className={styles.actions}>{directActions(item)}</div></div></article>; })}</div></section>}

    {tab === "management" && <section><div className={styles.managementGrid}><article className={styles.panel}><h2>زمان‌بندی استخراج افزایشی</h2><div className={styles.scheduleGrid}><label>وضعیت<select value={schedule.enabled?"enabled":"disabled"} onChange={(event)=>setSchedule({...schedule,enabled:event.target.value==="enabled"})}><option value="enabled">فعال</option><option value="disabled">غیرفعال</option></select></label><label>نوع برنامه<select value={schedule.cadence} onChange={(event)=>setSchedule({...schedule,cadence:event.target.value})}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label>{schedule.cadence==="daily"?<label>ساعت روزانه<input type="time" value={schedule.dailyTime} onChange={(event)=>setSchedule({...schedule,dailyTime:event.target.value})}/></label>:<label>هر چند ساعت یک‌بار<input type="number" min="1" max="168" value={schedule.intervalHours} onChange={(event)=>setSchedule({...schedule,intervalHours:Number(event.target.value)})}/></label>}</div><p>اجرای روزانه، ساعتی و دکمه «استخراج اکنون» افزایشی هستند و پس از رسیدن مطمئن به داده‌های قبلی متوقف می‌شوند.</p><div className={styles.actions}><button className={styles.primaryButton} onClick={()=>notify("استخراج افزایشی دستی در Preview شبیه‌سازی شد.")}>استخراج اکنون</button></div></article><article className={styles.panel}><h2>استخراج دستی بازه گذشته</h2><label>تعداد روز گذشته<input type="number" min="1" max="365" value={schedule.lookbackDays} onChange={(event)=>setSchedule({...schedule,lookbackDays:Number(event.target.value)})}/></label><p>در این حالت مشاهده داده مشترک باعث توقف نمی‌شود و تمام رکوردهای بازه دوباره کنترل می‌شوند.</p><button className={styles.primaryButton} onClick={()=>notify(`استخراج بازه ${fa.format(schedule.lookbackDays)} روز گذشته در Preview شبیه‌سازی شد.`)}>اجرای استخراج بازه‌دار</button></article></div><div className={styles.managementGrid} style={{marginTop:14}}>{[{name:"پروفایل شرکت",version:"v4",date:"۱۴۰۵/۰۵/۰۱"},{name:"نقش و دستورهای پایه",version:"v6",date:"۱۴۰۵/۰۵/۰۲"},{name:"پرامپت تحلیل",version:"v5",date:"۱۴۰۵/۰۵/۰۲"},{name:"کلیدواژه‌ها",version:"v8",date:"۱۴۰۵/۰۵/۰۳"},{name:"رزومه و سوابق",version:"v3",date:"۱۴۰۵/۰۴/۲۹"}].map((item)=><article className={styles.panel} key={item.name}><h3>{item.name}</h3><dl><div><dt>نسخه</dt><dd>{item.version}</dd></div><div><dt>تاریخ نسخه</dt><dd>{item.date}</dd></div></dl></article>)}</div></section>}

    {showDirectModal&&<div className={styles.backdrop} onMouseDown={()=>setShowDirectModal(false)}><section className={`${styles.modal} ${styles.largeModal}`} onMouseDown={(event)=>event.stopPropagation()}><header><div><small>ثبت اولیه بدون کد دائمی</small><h2>ثبت ارجاع مستقیم جدید</h2><p>رکورد ابتدا در «کل ارجاعات مستقیم» قرار می‌گیرد و پس از ورود به منتخب کد DIR دریافت می‌کند.</p></div><button type="button" onClick={()=>setShowDirectModal(false)}>×</button></header><form className={styles.modalForm} onSubmit={registerDirect}><div className={styles.formGrid}><label>عنوان<input name="title"/></label><label>کارفرما<input name="employer"/></label><label>نوع ارجاع<select name="opportunityType"><option>نیازمند تعیین</option><option>مذاکره مستقیم</option><option>دعوت محدود</option><option>رایزنی با کارفرما</option><option>معرفی مستقیم</option><option>ترک تشریفات</option></select></label><label>اهمیت<select name="importance" defaultValue="medium"><option value="low">کم</option><option value="medium">متوسط</option><option value="high">زیاد</option><option value="very_high">بسیار زیاد</option></select></label><label>حوزه تخصصی<input name="domain"/></label><label>استان<input name="province"/></label><label>شهر<input name="city"/></label><label>مهلت یا تاریخ هدف<input type="datetime-local" name="targetDeadline"/></label><label>مبلغ برآوردی ـ ریال<input name="estimatedValue" inputMode="numeric"/></label><label>احتمال تبدیل ـ درصد<input type="number" min="0" max="100" name="probability"/></label><label>مسئول<input name="responsible"/></label><label>محرمانگی<select name="confidentiality"><option>عادی</option><option>داخلی</option><option>محرمانه</option></select></label><label>نام رابط<input name="contactName"/></label><label>تلفن رابط<input name="contactPhone"/></label><label>ایمیل رابط<input type="email" name="contactEmail"/></label><label className={styles.wideField}>شرح و یادداشت<textarea name="description" rows={4}/></label></div><div className={styles.formActions}><button type="button" className={styles.secondaryButton} onClick={()=>setShowDirectModal(false)}>انصراف</button><button className={styles.primaryButton}>ثبت در کل ارجاعات مستقیم</button></div></form></section></div>}

    {selected&&<div className={styles.backdrop} onMouseDown={()=>setSelected(null)}><section className={styles.modal} onMouseDown={(event)=>event.stopPropagation()}><header><div><small>{selected.showCode&&selected.code?`${selected.code} · `:""}{selected.status}</small><h2>{selected.title}</h2><p>{selected.employer}</p></div><button onClick={()=>setSelected(null)}>×</button></header><div className={styles.modalBody}><h3>اسناد پرونده</h3>{selected.documents.length?selected.documents.map((document)=><p key={document}>• {document}</p>):<p>سندی ثبت نشده است.</p>}</div></section></div>}
  </main>;
}
