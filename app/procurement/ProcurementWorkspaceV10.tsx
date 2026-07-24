"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import ConnectorHealthBanner from "./ConnectorHealthBanner";
import ExtractionSourceControls from "./ExtractionSourceControls";
import styles from "./workspace-v4.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "reports" | "prompts" | "keywords" | "company" | "versions";
type Importance = "low" | "medium" | "high" | "very_high";
type NoticeStage = "" | "selected" | "preparing" | "submitted" | "results";
type DirectStage = "new" | "reviewing" | "selected" | "preparing" | "submitted" | "won" | "lost";

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
  documents: number;
};

type DirectReferral = {
  id: string;
  referenceCode: string | null;
  title: string;
  employer: string;
  opportunityType: string;
  domain: string;
  province: string;
  probability: number | null;
  importance: Importance;
  responsible: string;
  targetDeadline: string | null;
  stage: DirectStage;
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
const managementTabs: [ManagementView, string][] = [
  ["extraction", "استخراج و منابع"],
  ["reports", "گزارش استخراج"],
  ["prompts", "نقش و Prompt"],
  ["keywords", "کلیدواژه‌ها"],
  ["company", "پروفایل، صلاحیت و رزومه"],
  ["versions", "نسخه‌ها و فعال‌سازی"],
];
const importanceLabels: Record<Importance, string> = {
  low: "کم",
  medium: "متوسط",
  high: "زیاد",
  very_high: "بسیار زیاد",
};

const noticesSeed: Notice[] = [
  { id:"T1", referenceCode:"TND-10000", kind:"tender", title:"خدمات مشاوره طراحی و نظارت مجموعه اداری", employer:"شرکت توسعه عمران", province:"تهران", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net", publishedDate:"۱۴۰۵/۰۵/۰۱", deadline:"2026-07-25T16:00:00+03:30", importance:"very_high", recommended:true, stage:"selected", result:"", score:91, responsible:"محمد ملکی", nextAction:"تقسیم کار تهیه پیشنهاد", progress:35, documents:1 },
  { id:"T2", referenceCode:"TND-10001", kind:"tender", title:"مطالعات طرح جامع و برنامه‌ریزی فضایی", employer:"اداره کل راه و شهرسازی", province:"فارس", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-30T14:00:00+03:30", importance:"high", recommended:true, stage:"preparing", result:"", score:95, responsible:"کارشناس مناقصات", nextAction:"تهیه ساختار شکست خدمات", progress:62, documents:2 },
  { id:"T3", referenceCode:null, kind:"tender", title:"طراحی تأسیسات بیمارستان", employer:"دانشگاه علوم پزشکی", province:"البرز", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-27T12:00:00+03:30", importance:"medium", recommended:false, stage:"", result:"", score:null, responsible:"", nextAction:"بررسی اولیه", progress:0, documents:0 },
  { id:"T4", referenceCode:null, kind:"tender", title:"مطالعات بازآفرینی بافت شهری", employer:"شهرداری نمونه", province:"کرمان", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-08-02T15:00:00+03:30", importance:"high", recommended:true, stage:"", result:"", score:87, responsible:"", nextAction:"تصمیم مدیر", progress:0, documents:0 },
  { id:"I1", referenceCode:"INQ-10000", kind:"inquiry", title:"استعلام خدمات نقشه‌برداری", employer:"شهرداری منطقه", province:"تهران", source:"پارس‌نماد داده", sourceUrl:"https://www.parsnamaddata.com", publishedDate:"۱۴۰۵/۰۵/۰۲", deadline:"2026-07-23T13:00:00+03:30", importance:"high", recommended:true, stage:"selected", result:"", score:88, responsible:"کارشناس مناقصات", nextAction:"دریافت قیمت و تأیید مدیر", progress:70, documents:0 },
  { id:"I2", referenceCode:"INQ-10001", kind:"inquiry", title:"استعلام گزارش توجیهی و امکان‌سنجی", employer:"منطقه ویژه اقتصادی", province:"بوشهر", source:"هزاره", sourceUrl:"https://www.hezarehinfo.net", publishedDate:"۱۴۰۵/۰۵/۰۱", deadline:"2026-07-26T15:00:00+03:30", importance:"very_high", recommended:true, stage:"preparing", result:"", score:86, responsible:"واحد مطالعات", nextAction:"جلسه با کارشناس مالی", progress:48, documents:1 },
  { id:"I3", referenceCode:null, kind:"inquiry", title:"استعلام طراحی روشنایی محوطه صنعتی", employer:"شرکت تولیدی نمونه", province:"قزوین", source:"پارس‌نماد داده", sourceUrl:"https://www.parsnamaddata.com", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-07-24T10:00:00+03:30", importance:"medium", recommended:false, stage:"", result:"", score:null, responsible:"", nextAction:"دریافت پیوست فنی", progress:0, documents:0 },
  { id:"I4", referenceCode:null, kind:"inquiry", title:"استعلام مطالعات ترافیکی", employer:"سازمان حمل‌ونقل", province:"تهران", source:"ستاد ایران", sourceUrl:"https://etend.setadiran.ir", publishedDate:"۱۴۰۵/۰۵/۰۳", deadline:"2026-07-29T12:00:00+03:30", importance:"high", recommended:true, stage:"", result:"", score:84, responsible:"", nextAction:"تصمیم مدیر", progress:0, documents:0 },
];

const directSeed: DirectReferral[] = [
  { id:"D1", referenceCode:null, title:"رایزنی طرح توسعه پردیس اداری", employer:"گروه سرمایه‌گذاری پارس", opportunityType:"رایزنی با کارفرما", domain:"معماری اداری", province:"تهران", probability:40, importance:"high", responsible:"محمد ملکی", targetDeadline:null, stage:"new" },
  { id:"D2", referenceCode:null, title:"مطالعات امکان‌سنجی نیروگاه خورشیدی", employer:"شرکت انرژی نو", opportunityType:"معرفی مستقیم", domain:"امکان‌سنجی", province:"یزد", probability:55, importance:"medium", responsible:"توسعه کسب‌وکار", targetDeadline:"2026-08-10T12:00:00+03:30", stage:"reviewing" },
  { id:"D3", referenceCode:"DIR-10000", title:"دعوت محدود طراحی مجموعه درمانی", employer:"بنیاد توسعه سلامت", opportunityType:"دعوت محدود", domain:"معماری درمانی", province:"تهران", probability:80, importance:"very_high", responsible:"مدیر فنی", targetDeadline:"2026-07-22T12:00:00+03:30", stage:"submitted" },
];

const extractionHistory = [
  { time:"۱۴۰۵/۰۵/۰۳ ـ ۰۷:۳۰", source:"هزاره", type:"مناقصات", pages:10, records:200, fresh:20, updated:4, duplicate:176, status:"موفق" },
  { time:"۱۴۰۵/۰۵/۰۳ ـ ۰۷:۳۶", source:"هزاره", type:"استعلامات", pages:8, records:160, fresh:16, updated:3, duplicate:141, status:"موفق" },
  { time:"۱۴۰۵/۰۵/۰۳ ـ ۰۷:۴۱", source:"پارس‌نماد داده", type:"استعلامات", pages:5, records:250, fresh:12, updated:5, duplicate:233, status:"موفق" },
  { time:"۱۴۰۵/۰۵/۰۳ ـ ۰۷:۴۸", source:"ستاد ایران", type:"مناقصات", pages:2, records:60, fresh:8, updated:2, duplicate:50, status:"محدود به سقف" },
];

function urgency(value: string | null) {
  if (!value) return { tone:"unknown", label:"تاریخ نامشخص", remaining:"نامشخص" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone:"critical", label:"مهلت گذشته", remaining:`${fa.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone:"critical", label:"فوریت بحرانی", remaining:`${fa.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone:"high", label:"فوریت زیاد", remaining:`${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  if (hours <= 168) return { tone:"medium", label:"فوریت متوسط", remaining:`${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
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

const compactFilters = { display:"grid", gridTemplateColumns:"minmax(230px,2fr) repeat(auto-fit,minmax(125px,1fr))", gap:8, padding:10, border:"1px solid rgba(15,23,42,.12)", borderRadius:12, background:"#f8fafc", marginBottom:12 } as const;
const inputStyle = { width:"100%", minHeight:36, border:"1px solid rgba(15,23,42,.16)", borderRadius:9, padding:"6px 9px", background:"white" } as const;
const sourceBadgeStyle = { display:"inline-flex", alignItems:"center", minHeight:22, padding:"2px 7px", borderRadius:999, border:"1px solid rgba(15,118,110,.22)", background:"#ecfdf5", color:"#0f766e", fontSize:11, fontWeight:700, textDecoration:"none", whiteSpace:"nowrap" } as const;

export default function ProcurementWorkspaceV10() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [provinceFilter, setProvinceFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [directTypeFilter, setDirectTypeFilter] = useState("");
  const [schedule, setSchedule] = useState({ enabled:true, cadence:"daily", dailyTime:"07:30", intervalHours:1, lookbackDays:7 });
  const [message, setMessage] = useState("");

  const noticeViews: [WorkflowView, string][] = [["all", viewLabel(tab, "all")], ...standardViews];
  const directViews: [WorkflowView, string][] = [["all", viewLabel("direct", "all")], ...standardViews];

  const filteredNotices = useMemo(() => noticesSeed.filter((item) =>
    (tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry") &&
    noticeMatches(item, noticeView) &&
    (!search || `${item.referenceCode || ""} ${item.title} ${item.employer} ${item.province}`.includes(search)) &&
    (!sourceFilter || item.source === sourceFilter) &&
    (!provinceFilter || item.province === provinceFilter) &&
    (!importanceFilter || item.importance === importanceFilter)
  ), [tab, noticeView, search, sourceFilter, provinceFilter, importanceFilter]);

  const filteredDirect = useMemo(() => directSeed.filter((item) =>
    directMatches(item, directView) &&
    (!search || `${item.referenceCode || ""} ${item.title} ${item.employer} ${item.domain}`.includes(search)) &&
    (!provinceFilter || item.province === provinceFilter) &&
    (!importanceFilter || item.importance === importanceFilter) &&
    (!directTypeFilter || item.opportunityType === directTypeFilter)
  ), [directView, search, provinceFilter, importanceFilter, directTypeFilter]);

  const recommendedCount = noticesSeed.filter((item) => item.recommended && !item.stage).length + directSeed.filter((item) => item.stage === "reviewing").length;
  const selectedCount = noticesSeed.filter((item) => ["selected", "preparing"].includes(item.stage)).length + directSeed.filter((item) => ["selected", "preparing"].includes(item.stage)).length;
  const submittedCount = noticesSeed.filter((item) => item.stage === "submitted").length + directSeed.filter((item) => item.stage === "submitted").length;
  const urgentCount = noticesSeed.filter((item) => ["critical", "high"].includes(urgency(item.deadline).tone) && item.stage !== "results").length;
  const activeCases = [
    ...noticesSeed.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title:item.title, subtitle:`${item.kind === "tender" ? "مناقصه" : "استعلام"} · ${item.employer}`, stage:item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next:item.nextAction, deadline:item.deadline })),
    ...directSeed.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title:item.title, subtitle:`ارجاع مستقیم · ${item.employer}`, stage:item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next:"پیگیری پرونده", deadline:item.targetDeadline })),
  ];

  function resetFilters() {
    setSearch("");
    setSourceFilter("");
    setProvinceFilter("");
    setImportanceFilter("");
    setDirectTypeFilter("");
  }

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 3200);
  }

  function registerDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    notify("ارجاع جدید در Preview ثبت شد؛ محیط واقعی تغییر نکرد.");
    event.currentTarget.reset();
  }

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}>
      <div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1><p>ساختار مدیریتی تأییدشده همراه با قابلیت‌های تکمیلی جدید</p></div>
      <Link href="/">بازگشت به سامانه</Link>
    </header>
    <div className={styles.banner}><b>Preview تعاملی</b><span>فقط موارد درخواستی به ساختار قبلی افزوده شده‌اند.</span></div>
    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); resetFilters(); setNoticeView("all"); setDirectView("all"); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article className={styles.kpi}><span>فراخوان جدید</span><b>{fa.format(24)}</b><small>از آخرین استخراج</small></article>
        <article className={styles.kpi}><span>تحلیل‌نشده</span><b>{fa.format(noticesSeed.filter((item) => item.score == null).length)}</b><small>در انتظار تحلیل</small></article>
        <article className={styles.kpi}><span>پیشنهادی</span><b>{fa.format(recommendedCount)}</b><small>نیازمند تصمیم انسانی</small></article>
        <article className={styles.kpi}><span>منتخب</span><b>{fa.format(selectedCount)}</b><small>پرونده در جریان</small></article>
        <article className={styles.kpi}><span>ارسال‌شده</span><b>{fa.format(submittedCount)}</b><small>در انتظار نتیجه</small></article>
        <article className={styles.kpi}><span>نزدیک مهلت</span><b>{fa.format(urgentCount)}</b><small>نیازمند اقدام فوری</small></article>
        <article className={styles.kpi}><span>ارجاع مستقیم فعال</span><b>{fa.format(3)}</b><small>ثبت اولیه تا ارسال</small></article>
        <article className={styles.kpi}><span>نتیجه موفق</span><b>{fa.format(1)}</b><small>آماده پیش‌نویس قرارداد</small></article>
      </div>
      <div className={styles.dashboardGrid}>
        <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>۳ اقدام پیگیری عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>{fa.format(urgentCount)} پرونده نزدیک به مهلت</span><span>۱ پرونده ارسال‌شده بدون پیگیری نتیجه</span></div></article>
        <article className={styles.panel}><h2>قیف مدیریتی</h2><div className={styles.funnel}><span>استخراج و ثبت‌شده</span><span>پیشنهادی {fa.format(recommendedCount)}</span><span>منتخب {fa.format(selectedCount)}</span><span>ارسال‌شده {fa.format(submittedCount)}</span><span>نتیجه موفق ۱</span></div></article>
        <article className={styles.panel}><h2>برد و باخت</h2><div className={styles.outcomeGrid}><div><b>۱</b><span>موفق</span></div><div><b>۱</b><span>ناموفق</span></div><div><b>۶۷٪</b><span>نرخ موفقیت نمونه</span></div><div><b>۱</b><span>پیش‌نویس قرارداد آینده</span></div></div></article>
        <article className={styles.panel}><h2>جمع‌بندی مدیریتی ChatGPT</h2><p>طرح جامع فارس بالاترین تناسب را دارد. استعلام نقشه‌برداری تهران فوریت زیادی دارد. ارجاع مستقیم پردیس اداری هنوز برای تصمیم مدیر در مرحله اولیه است.</p><div className={styles.summaryTags}><span>اقدام امروز: استعلام تهران</span><span>فرصت راهبردی: طرح جامع فارس</span><span>نیازمند تصمیم: پردیس اداری</span></div></article>
      </div>
      <article className={`${styles.panel} ${styles.activeCases}`}><div className={styles.sectionHeading}><div><span>انتهای داشبورد</span><h2>پرونده‌های فعال</h2></div><small>مناقصات، استعلامات و ارجاعات مستقیم منتخب یا ارسال‌شده</small></div><div className={styles.caseTable}>{activeCases.map((item) => { const u=urgency(item.deadline); return <button key={`${item.title}-${item.subtitle}`}><span><b>{item.title}</b><small>{item.subtitle}</small></span><span><b>{item.stage}</b><small>{item.next}</small></span><span className={`${styles.urgency} ${styles[u.tone]}`}><b>{u.label}</b><small>{u.remaining}</small></span></button>; })}</div></article>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <div className={styles.views}>{noticeViews.map(([id, label]) => <button key={id} className={noticeView === id ? styles.active : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div>
      <div style={compactFilters}>
        <label>جست‌وجو<input style={inputStyle} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، استان یا کد" /></label>
        <label>منبع<select style={inputStyle} value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">همه منابع</option>{[...new Set(noticesSeed.map((item) => item.source))].map((source) => <option key={source}>{source}</option>)}</select></label>
        <label>استان<select style={inputStyle} value={provinceFilter} onChange={(event) => setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(noticesSeed.map((item) => item.province))].map((province) => <option key={province}>{province}</option>)}</select></label>
        <label>اهمیت<select style={inputStyle} value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <div style={{display:"flex",alignItems:"end",gap:8}}><button className={styles.secondaryButton} onClick={resetFilters}>پاک‌کردن</button><b>{fa.format(filteredNotices.length)}</b></div>
      </div>
      <div className={styles.recordList}>{filteredNotices.map((item,index) => { const u=urgency(item.deadline); return <article className={styles.record} key={item.id}>
        <div>
          <div className={styles.recordTop}>
            <small><b>ردیف {fa.format(index+1)}</b>{item.referenceCode && noticeView !== "all" && noticeView !== "recommended" && <> · <span className={styles.codeBadge}>{item.referenceCode}</span></>} · انتشار {item.publishedDate}</small>
            <div style={{display:"flex",gap:6,alignItems:"center",marginInlineStart:"auto"}}><a href={item.sourceUrl} target="_blank" rel="noreferrer" style={sourceBadgeStyle}>{item.source}</a><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div>
          </div>
          <h3>{item.title}</h3><p>{item.employer}</p>
          <div className={styles.facts}><span>{item.province}</span><span>اهمیت: {importanceLabels[item.importance]}</span><span>{u.remaining}</span><span>اولویت: {item.score ?? "تحلیل نشده"}</span>{item.documents > 0 && <span>{fa.format(item.documents)} سند</span>}</div>
        </div>
        <div className={styles.decision}><span className={styles.stage}>{item.result || item.stage || (item.recommended ? "پیشنهادی" : viewLabel(tab,"all"))}</span><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div></dl><div className={styles.actions}><button className={styles.secondaryButton}>مشاهده</button>{!item.stage && <button className={styles.primaryButton}>افزودن به پیشنهادی</button>}</div></div>
      </article>; })}</div>
    </section>}

    {tab === "direct" && <section>
      <div style={{display:"flex",justifyContent:"flex-end",marginBottom:12}}><button className={styles.primaryButton} onClick={() => notify("فرم ثبت ارجاع در Preview باز می‌شود.")}>ثبت ارجاع مستقیم جدید</button></div>
      <div className={styles.views}>{directViews.map(([id,label]) => <button key={id} className={directView === id ? styles.active : ""} onClick={() => setDirectView(id)}>{label}</button>)}</div>
      <div style={compactFilters}>
        <label>جست‌وجو<input style={inputStyle} value={search} onChange={(event)=>setSearch(event.target.value)} placeholder="عنوان، کارفرما، حوزه یا کد" /></label>
        <label>نوع ارجاع<select style={inputStyle} value={directTypeFilter} onChange={(event)=>setDirectTypeFilter(event.target.value)}><option value="">همه انواع</option>{[...new Set(directSeed.map((item)=>item.opportunityType))].map((type)=><option key={type}>{type}</option>)}</select></label>
        <label>استان<select style={inputStyle} value={provinceFilter} onChange={(event)=>setProvinceFilter(event.target.value)}><option value="">همه استان‌ها</option>{[...new Set(directSeed.map((item)=>item.province))].map((province)=><option key={province}>{province}</option>)}</select></label>
        <label>اهمیت<select style={inputStyle} value={importanceFilter} onChange={(event)=>setImportanceFilter(event.target.value)}><option value="">همه سطوح</option>{Object.entries(importanceLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <b style={{alignSelf:"end"}}>{fa.format(filteredDirect.length)} رکورد</b>
      </div>
      <div className={styles.recordList}>{filteredDirect.map((item,index)=>{const u=urgency(item.targetDeadline);return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small><b>ردیف {fa.format(index+1)}</b>{item.referenceCode&&directView!=="all"&&directView!=="recommended"&&<> · <span className={styles.codeBadge}>{item.referenceCode}</span></>} · {item.opportunityType}</small><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{item.domain}</span><span>{item.province}</span><span>اهمیت: {importanceLabels[item.importance]}</span>{item.probability!==null&&<span>احتمال تبدیل: {fa.format(item.probability)}٪</span>}</div></div><div className={styles.decision}><span className={styles.stage}>{item.stage === "new" ? "کل ارجاعات مستقیم" : item.stage === "reviewing" ? "پیشنهادی" : item.stage === "submitted" ? "ارسال‌شده" : "منتخب"}</span><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div></dl><div className={styles.actions}><button className={styles.secondaryButton}>مشاهده</button></div></div></article>})}</div>
      <form onSubmit={registerDirect} style={{display:"none"}}><button>ثبت</button></form>
    </section>}

    {tab === "management" && <section>
      <div className={styles.sectionHeading}><div><span>تنظیمات کنترل‌شده</span><h2>مدیریت زیرسامانه</h2></div><small>ساختار زیرتب‌های تأییدشده قبلی حفظ شده است.</small></div>
      <div className={styles.managementTabs}>{managementTabs.map(([id,label])=><button key={id} className={managementView===id?styles.active:""} onClick={()=>setManagementView(id)}>{label}</button>)}</div>

      {managementView === "extraction" && <div style={{display:"grid",gap:14}}>
        <ExtractionSourceControls />
        <div className={styles.managementGrid}>
          <article className={styles.panel}><h2>زمان‌بندی استخراج افزایشی</h2><div className={styles.scheduleGrid}><label>وضعیت<select value={schedule.enabled?"enabled":"disabled"} onChange={(event)=>setSchedule({...schedule,enabled:event.target.value==="enabled"})}><option value="enabled">فعال</option><option value="disabled">غیرفعال</option></select></label><label>نوع برنامه<select value={schedule.cadence} onChange={(event)=>setSchedule({...schedule,cadence:event.target.value})}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label>{schedule.cadence==="daily"?<label>ساعت روزانه<input type="time" value={schedule.dailyTime} onChange={(event)=>setSchedule({...schedule,dailyTime:event.target.value})}/></label>:<label>هر چند ساعت<input type="number" min="1" max="168" value={schedule.intervalHours} onChange={(event)=>setSchedule({...schedule,intervalHours:Number(event.target.value)})}/></label>}</div><p>اجرای روزانه، ساعتی و «استخراج اکنون» افزایشی هستند.</p><button className={styles.primaryButton} onClick={()=>notify("استخراج افزایشی در Preview شبیه‌سازی شد.")}>استخراج اکنون</button></article>
          <article className={styles.panel}><h2>استخراج دستی بازه گذشته</h2><label>تعداد روز گذشته<input type="number" min="1" max="365" value={schedule.lookbackDays} onChange={(event)=>setSchedule({...schedule,lookbackDays:Number(event.target.value)})}/></label><p>در این حالت رسیدن به داده مشترک باعث توقف نمی‌شود.</p><button className={styles.primaryButton} onClick={()=>notify(`استخراج ${fa.format(schedule.lookbackDays)} روز گذشته در Preview شبیه‌سازی شد.`)}>اجرای بازه‌دار</button></article>
        </div>
      </div>}

      {managementView === "reports" && <div style={{display:"grid",gap:14}}>
        <ConnectorHealthBanner embedded />
        <article className={styles.panel}><div className={styles.sectionHeading}><div><span>سوابق اجرا</span><h2>آخرین استخراج‌ها</h2></div><small>تعداد صفحه، رکورد و نتیجه هر اجرا</small></div><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{["زمان","منبع","نوع","صفحه","رکورد","جدید","به‌روزشده","تکراری","وضعیت"].map((head)=><th key={head} style={{textAlign:"right",padding:9,borderBottom:"1px solid #e2e8f0"}}>{head}</th>)}</tr></thead><tbody>{extractionHistory.map((run)=><tr key={`${run.time}-${run.source}-${run.type}`}><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.time}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.source}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{run.type}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.pages)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.records)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.fresh)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.updated)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9"}}>{fa.format(run.duplicate)}</td><td style={{padding:9,borderBottom:"1px solid #f1f5f9",fontWeight:700}}>{run.status}</td></tr>)}</tbody></table></div></article>
      </div>}

      {managementView === "prompts" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>نقش و Prompt</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>نقش تحلیلگر<textarea rows={4} defaultValue="تحلیلگر ارشد مناقصات، استعلامات و فرصت‌های کسب‌وکار شرکت مهندسین مشاور طرح و برنامه پارس" /></label><label>دستورهای پایه<textarea rows={5} defaultValue="تحلیل بر مبنای صلاحیت‌ها، ظرفیت اجرایی، زمان، ریسک و سوابق شرکت انجام شود." /></label><label>Prompt تحلیل<textarea rows={7} defaultValue="تناسب فرصت، مهلت، اسناد، ریسک و اقدام پیشنهادی را بررسی کن." /></label><label className={styles.fileBox}>بارگذاری مرجع Prompt<input type="file" multiple /><small>pdf، docx، txt یا md</small></label></div></article>}

      {managementView === "keywords" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>کلیدواژه‌ها</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>کلیدواژه‌های فعال<textarea rows={10} defaultValue={"خدمات مشاوره\nمطالعات\nامکان‌سنجی\nطراحی معماری\nنظارت\nطرح جامع\nتأسیسات"} /></label><label>کلیدواژه‌های حذف یا احتیاط<textarea rows={7} defaultValue={"تأمین کالا\nاجرای صرف\nخرید تجهیزات"} /></label><label className={styles.fileBox}>بارگذاری فایل کلیدواژه<input type="file" multiple /><small>txt، csv یا xlsx</small></label></div></article>}

      {managementView === "company" && <article className={styles.lockedCard}><div className={styles.lockedHeader}><div><h2>پروفایل، صلاحیت‌ها و رزومه</h2><span className={styles.lockBadge}>نسخه فعال و قفل</span></div><button className={styles.secondaryButton}>ویرایش</button></div><div className={styles.fields}><label>پروفایل خلاصه شرکت<textarea rows={5} defaultValue="شرکت مهندسین مشاور طرح و برنامه پارس؛ فعال در معماری، شهرسازی، تأسیسات و مطالعات امکان‌سنجی." /></label><label>صلاحیت‌ها<textarea rows={7} defaultValue="معماری، شهرسازی، تأسیسات برق و مکانیک، مطالعات جغرافیایی و برنامه‌ریزی فضایی" /></label><label>سوابق و تجربیات<textarea rows={7} defaultValue="سوابق طراحی، نظارت، طرح جامع، امکان‌سنجی و مطالعات فنی و اقتصادی" /></label><label className={styles.fileBox}>بارگذاری پروفایل یا رزومه<input type="file" multiple /><small>pdf، docx، txt یا md</small></label></div></article>}

      {managementView === "versions" && <div className={styles.managementGrid}>{[
        ["پروفایل شرکت","نسخه ۴","۱۴۰۵/۰۵/۰۱"],
        ["نقش و دستورهای پایه","نسخه ۶","۱۴۰۵/۰۵/۰۲"],
        ["پرامپت تحلیل","نسخه ۵","۱۴۰۵/۰۵/۰۲"],
        ["کلیدواژه‌ها","نسخه ۸","۱۴۰۵/۰۵/۰۳"],
        ["رزومه و سوابق","نسخه ۳","۱۴۰۵/۰۴/۲۹"],
      ].map(([name,version,date])=><article className={styles.panel} key={name}><h3>{name}</h3><dl><div><dt>نسخه</dt><dd>{version}</dd></div><div><dt>تاریخ نسخه</dt><dd>{date}</dd></div><div><dt>وضعیت</dt><dd>فعال و قفل</dd></div></dl><button className={styles.secondaryButton}>مشاهده تاریخچه</button></article>)}</div>}
    </section>}
  </main>;
}
