"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import styles from "./workspace-v4.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "prompts" | "keywords" | "company" | "versions";
type LockSection = "schedule" | "prompts" | "keywords" | "company";
type UrgencyTone = "critical" | "high" | "medium" | "normal" | "unknown";

type Notice = {
  id: string;
  kind: "tender" | "inquiry";
  title: string;
  employer: string;
  province: string;
  source: string;
  deadline: string | null;
  recommended: boolean;
  stage: "" | "selected" | "preparing" | "submitted" | "results";
  result: "" | "برنده" | "ناموفق" | "لغوشده";
  score: number | null;
  responsible: string;
  nextAction: string;
  progress: number;
};

type DirectReferralStage = "new" | "reviewing" | "following_up" | "negotiating" | "selected" | "preparing" | "submitted" | "won" | "lost" | "stopped" | "deferred";

type DirectReferral = {
  id: string;
  title: string;
  employer: string;
  opportunityType: string;
  domain: string;
  province: string;
  city: string;
  referenceNumber: string;
  sourceText: string;
  description: string;
  estimatedValue: string;
  probability: number | null;
  responsible: string;
  nextAction: string;
  nextActionDue: string | null;
  targetDeadline: string | null;
  submissionMethod: string;
  contactName: string;
  contactPhone: string;
  contactEmail: string;
  confidentiality: string;
  stage: DirectReferralStage;
};

type ContextEditor = {
  role: string;
  base: string;
  prompt: string;
  activeKeywords: string;
  excludedKeywords: string;
  companyProfile: string;
  qualifications: string;
  experience: string;
};

const fa = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

const seedNotices: Notice[] = [
  { id: "T1", kind: "tender", title: "خدمات مشاوره طراحی و نظارت مجموعه اداری", employer: "شرکت توسعه عمران", province: "تهران", source: "هزاره", deadline: "2026-07-25T16:00:00+03:30", recommended: true, stage: "selected", result: "", score: 91, responsible: "محمد ملکی", nextAction: "تقسیم کار تهیه پیشنهاد", progress: 35 },
  { id: "T2", kind: "tender", title: "مطالعات طرح جامع و برنامه‌ریزی فضایی", employer: "اداره کل راه و شهرسازی", province: "فارس", source: "پارس نماد داده", deadline: "2026-07-30T14:00:00+03:30", recommended: true, stage: "preparing", result: "", score: 95, responsible: "کارشناس مناقصات", nextAction: "تهیه ساختار شکست خدمات", progress: 62 },
  { id: "T3", kind: "tender", title: "طراحی تأسیسات بیمارستان", employer: "دانشگاه علوم پزشکی", province: "البرز", source: "هزاره", deadline: "2026-07-27T12:00:00+03:30", recommended: false, stage: "", result: "", score: null, responsible: "", nextAction: "بررسی اولیه", progress: 0 },
  { id: "T4", kind: "tender", title: "مطالعات امکان‌سنجی شهرک صنعتی", employer: "شرکت شهرک‌های صنعتی", province: "آذربایجان شرقی", source: "پارس نماد داده", deadline: "2026-07-22T15:00:00+03:30", recommended: true, stage: "submitted", result: "", score: 82, responsible: "توسعه کسب‌وکار", nextAction: "پیگیری نتیجه", progress: 100 },
  { id: "T5", kind: "tender", title: "طراحی معماری مجتمع آموزشی", employer: "سازمان نوسازی مدارس", province: "قم", source: "هزاره", deadline: "2026-07-10T12:00:00+03:30", recommended: true, stage: "results", result: "برنده", score: 94, responsible: "مدیرعامل", nextAction: "ایجاد پیش‌نویس قرارداد", progress: 100 },
  { id: "I1", kind: "inquiry", title: "استعلام خدمات نقشه‌برداری", employer: "شهرداری منطقه", province: "تهران", source: "پارس نماد داده", deadline: "2026-07-23T13:00:00+03:30", recommended: true, stage: "selected", result: "", score: 88, responsible: "کارشناس مناقصات", nextAction: "دریافت قیمت و تأیید مدیر", progress: 70 },
  { id: "I2", kind: "inquiry", title: "استعلام گزارش توجیهی و امکان‌سنجی", employer: "منطقه ویژه اقتصادی", province: "بوشهر", source: "هزاره", deadline: "2026-07-26T15:00:00+03:30", recommended: true, stage: "preparing", result: "", score: 86, responsible: "واحد مطالعات", nextAction: "جلسه با کارشناس مالی", progress: 48 },
  { id: "I3", kind: "inquiry", title: "استعلام طراحی روشنایی محوطه صنعتی", employer: "شرکت تولیدی نمونه", province: "قزوین", source: "پارس نماد داده", deadline: "2026-07-24T10:00:00+03:30", recommended: false, stage: "", result: "", score: null, responsible: "", nextAction: "دریافت پیوست فنی", progress: 0 },
  { id: "I4", kind: "inquiry", title: "استعلام بازنگری نقشه‌های معماری", employer: "شرکت عمران و مسکن", province: "مازندران", source: "هزاره", deadline: "2026-07-18T12:00:00+03:30", recommended: true, stage: "results", result: "ناموفق", score: 79, responsible: "واحد فنی", nextAction: "مرور علت باخت", progress: 100 },
];

const seedDirect: DirectReferral[] = [
  { id: "D1", title: "رایزنی طرح توسعه پردیس اداری", employer: "گروه سرمایه‌گذاری پارس", opportunityType: "رایزنی با کارفرما", domain: "معماری اداری", province: "تهران", city: "تهران", referenceNumber: "", sourceText: "جلسه معرفی", description: "طراحی و توسعه پردیس اداری", estimatedValue: "", probability: 40, responsible: "محمد ملکی", nextAction: "بررسی اولیه و تکمیل اطلاعات", nextActionDue: "2026-07-23T11:00:00+03:30", targetDeadline: null, submissionMethod: "", contactName: "نماینده کارفرما", contactPhone: "", contactEmail: "", confidentiality: "داخلی", stage: "new" },
  { id: "D2", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی نو", opportunityType: "معرفی مستقیم", domain: "امکان‌سنجی", province: "یزد", city: "", referenceNumber: "", sourceText: "معرفی شریک تجاری", description: "مطالعات فنی و اقتصادی", estimatedValue: "", probability: 55, responsible: "توسعه کسب‌وکار", nextAction: "هماهنگی جلسه فنی", nextActionDue: "2026-07-25T10:00:00+03:30", targetDeadline: "2026-08-10T12:00:00+03:30", submissionMethod: "ایمیل", contactName: "", contactPhone: "", contactEmail: "", confidentiality: "داخلی", stage: "reviewing" },
  { id: "D3", title: "دعوت محدود طراحی مجموعه درمانی", employer: "بنیاد توسعه سلامت", opportunityType: "دعوت محدود", domain: "معماری درمانی", province: "تهران", city: "", referenceNumber: "HL-1405-12", sourceText: "دعوت‌نامه", description: "طراحی معماری و تأسیسات", estimatedValue: "78000000000", probability: 80, responsible: "مدیر فنی", nextAction: "پیگیری دریافت پیشنهاد", nextActionDue: "2026-07-24T09:00:00+03:30", targetDeadline: "2026-07-22T12:00:00+03:30", submissionMethod: "ایمیل", contactName: "دبیرخانه بنیاد", contactPhone: "", contactEmail: "", confidentiality: "داخلی", stage: "submitted" },
  { id: "D4", title: "طراحی مرکز خدمات شهری", employer: "شرکت عمران شهری", opportunityType: "مذاکره مستقیم", domain: "معماری", province: "البرز", city: "کرج", referenceNumber: "", sourceText: "مذاکره مدیرعامل", description: "", estimatedValue: "62000000000", probability: 100, responsible: "مدیرعامل", nextAction: "ایجاد پیش‌نویس قرارداد", nextActionDue: "2026-07-26T10:00:00+03:30", targetDeadline: null, submissionMethod: "", contactName: "", contactPhone: "", contactEmail: "", confidentiality: "محرمانه", stage: "won" },
];

const tabs: [Tab, string][] = [["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"], ["direct", "ارجاعات مستقیم"], ["management", "مدیریت زیرسامانه"]];
const views: [WorkflowView, string][] = [["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"], ["submitted", "ارسال‌شده"], ["results", "نتایج"]];
const managementTabs: [ManagementView, string][] = [["extraction", "استخراج و منابع"], ["prompts", "نقش و Prompt"], ["keywords", "کلیدواژه‌ها"], ["company", "پروفایل، صلاحیت و رزومه"], ["versions", "نسخه‌ها و فعال‌سازی"]];

function urgency(value: string | null) {
  if (!value) return { tone: "unknown" as UrgencyTone, label: "تاریخ نامشخص", remaining: "نامشخص" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone: "critical" as UrgencyTone, label: "مهلت گذشته", remaining: `${fa.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone: "critical" as UrgencyTone, label: "فوریت بحرانی", remaining: `${fa.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone: "high" as UrgencyTone, label: "فوریت زیاد", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  if (hours <= 168) return { tone: "medium" as UrgencyTone, label: "فوریت متوسط", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  return { tone: "normal" as UrgencyTone, label: "عادی", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
}

function directLabel(stage: DirectReferralStage) {
  return ({ new: "ثبت‌شده در همه", reviewing: "پیشنهادی", following_up: "پیشنهادی · در حال پیگیری", negotiating: "پیشنهادی · در حال مذاکره", selected: "منتخب", preparing: "منتخب · در دست تهیه", submitted: "ارسال‌شده", won: "موفق", lost: "ناموفق", stopped: "متوقف‌شده", deferred: "به تعویق افتاده" } as Record<DirectReferralStage, string>)[stage];
}

function directMatches(item: DirectReferral, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return ["reviewing", "following_up", "negotiating"].includes(item.stage);
  if (view === "selected") return ["selected", "preparing"].includes(item.stage);
  if (view === "submitted") return item.stage === "submitted";
  return ["won", "lost", "stopped", "deferred"].includes(item.stage);
}

function noticeMatches(item: Notice, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return item.recommended && !item.stage;
  if (view === "selected") return item.stage === "selected" || item.stage === "preparing";
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "results";
}

export default function ProcurementWorkspaceV4() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [notices, setNotices] = useState(seedNotices);
  const [direct, setDirect] = useState(seedDirect);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<{ title: string; employer: string; status: string; details: string; deadline: string | null } | null>(null);
  const [editing, setEditing] = useState<Record<LockSection, boolean>>({ schedule: false, prompts: false, keywords: false, company: false });
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string[]>>({ prompt: [], keywords: [], company: [], resume: [] });
  const [context, setContext] = useState<ContextEditor>({ role: "تحلیلگر ارشد مناقصات، استعلامات و ارجاعات مستقیم", base: "تحلیل بر اساس صلاحیت، ظرفیت، زمان، ریسک و سوابق انجام شود و نتیجه فقط پیش‌نویس باشد.", prompt: "هر فرصت را از نظر تناسب، زمان، شرایط، ریسک، سوابق و اقدام پیشنهادی تحلیل کن.", activeKeywords: "طراحی معماری\nنظارت\nطرح جامع\nامکان‌سنجی", excludedKeywords: "تأمین کالا\nاجرای صرف", companyProfile: "شرکت مهندسین مشاور طرح و برنامه پارس", qualifications: "رتبه ۳ معماری\nرتبه ۳ شهرسازی\nرتبه ۳ تأسیسات برق و مکانیک", experience: "پروژه‌های اداری و آموزشی\nمطالعات شهری و منطقه‌ای\nمطالعات امکان‌سنجی" });
  const [schedule, setSchedule] = useState({ enabled: false, cadence: "daily", dailyTime: "17:00", intervalMinutes: 60, delayMinutes: 60, timezone: "Asia/Tehran" });

  const filteredNotices = useMemo(() => notices.filter((item) => {
    const kindMatches = tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry";
    return kindMatches && noticeMatches(item, noticeView) && (!search || `${item.title} ${item.employer} ${item.province}`.includes(search));
  }), [notices, noticeView, search, tab]);

  const filteredDirect = useMemo(() => direct.filter((item) => directMatches(item, directView) && (!search || `${item.title} ${item.employer} ${item.province} ${item.domain}`.includes(search))), [direct, directView, search]);

  const recommendedCount = notices.filter((item) => item.recommended && !item.stage).length + direct.filter((item) => ["reviewing", "following_up", "negotiating"].includes(item.stage)).length;
  const selectedCount = notices.filter((item) => ["selected", "preparing"].includes(item.stage)).length + direct.filter((item) => ["selected", "preparing"].includes(item.stage)).length;
  const submittedCount = notices.filter((item) => item.stage === "submitted").length + direct.filter((item) => item.stage === "submitted").length;
  const successCount = notices.filter((item) => item.result === "برنده").length + direct.filter((item) => item.stage === "won").length;
  const urgentCount = notices.filter((item) => ["critical", "high"].includes(urgency(item.deadline).tone) && item.stage !== "results").length + direct.filter((item) => ["critical", "high"].includes(urgency(item.targetDeadline || item.nextActionDue).tone) && !["won", "lost", "stopped", "deferred"].includes(item.stage)).length;
  const activeCases = [
    ...notices.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title, subtitle: `${item.kind === "tender" ? "مناقصه" : "استعلام"} · ${item.employer}`, stage: item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next: item.nextAction, deadline: item.deadline })),
    ...direct.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title || "ارجاع مستقیم بدون عنوان", subtitle: `ارجاع مستقیم · ${item.employer || "کارفرما ثبت نشده"}`, stage: item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next: item.nextAction || "اقدام بعدی ثبت نشده", deadline: item.targetDeadline || item.nextActionDue })),
  ];

  function notify(text: string) { setMessage(text); window.setTimeout(() => setMessage(""), 3500); }
  function updateNotice(id: string, change: Partial<Notice>) { setNotices((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }
  function updateDirect(id: string, change: Partial<DirectReferral>) { setDirect((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }

  function handleContextFile(key: string, event: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(event.target.files || []).map((file) => file.name);
    setUploadedFiles((current) => ({ ...current, [key]: [...(current[key] || []), ...names] }));
  }

  function registerDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form.entries());
    const hasMeaningfulValue = Object.values(values).some((value) => String(value).trim());
    if (!hasMeaningfulValue) { notify("حداقل یک اطلاعات درباره ارجاع مستقیم وارد کنید."); return; }
    const item: DirectReferral = {
      id: `D-${Date.now()}`,
      title: String(form.get("title") || "").trim(), employer: String(form.get("employer") || "").trim(), opportunityType: String(form.get("opportunityType") || "نیازمند تعیین"), domain: String(form.get("domain") || "").trim(), province: String(form.get("province") || "").trim(), city: String(form.get("city") || "").trim(), referenceNumber: String(form.get("referenceNumber") || "").trim(), sourceText: String(form.get("sourceText") || "").trim(), description: String(form.get("description") || "").trim(), estimatedValue: String(form.get("estimatedValue") || "").trim(), probability: form.get("probability") ? Number(form.get("probability")) : null, responsible: String(form.get("responsible") || "").trim(), nextAction: String(form.get("nextAction") || "").trim(), nextActionDue: String(form.get("nextActionDue") || "") || null, targetDeadline: String(form.get("targetDeadline") || "") || null, submissionMethod: String(form.get("submissionMethod") || "").trim(), contactName: String(form.get("contactName") || "").trim(), contactPhone: String(form.get("contactPhone") || "").trim(), contactEmail: String(form.get("contactEmail") || "").trim(), confidentiality: String(form.get("confidentiality") || "داخلی"), stage: "new",
    };
    setDirect((items) => [item, ...items]);
    event.currentTarget.reset();
    setDirectView("all");
    notify("ارجاع مستقیم در فهرست «همه» ثبت شد و هنوز پیشنهادی نیست.");
  }

  function noticeActions(item: Notice) {
    if (noticeView === "all") return <>{!item.recommended && !item.stage && <button className={styles.primaryButton} onClick={() => { updateNotice(item.id, { recommended: true }); notify("به پیشنهادی اضافه شد."); }}>افزودن به پیشنهادی</button>}<button className={styles.secondaryButton} onClick={() => setSelected({ title: item.title, employer: item.employer, status: item.stage || (item.recommended ? "پیشنهادی" : "همه"), details: item.nextAction, deadline: item.deadline })}>مشاهده</button></>;
    if (noticeView === "recommended") return <><button className={styles.primaryButton} onClick={() => updateNotice(item.id, { stage: "selected", responsible: item.responsible || "محمد ملکی", progress: 5 })}>انتخاب</button><button className={styles.secondaryButton}>پیگیری</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { recommended: false })}>حذف</button></>;
    if (noticeView === "selected") return <><button className={styles.secondaryButton}>ثبت پیشرفت</button><button className={styles.primaryButton} onClick={() => updateNotice(item.id, { stage: "submitted", progress: 100 })}>ارسال شد</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { stage: "", recommended: true, progress: 0 })}>حذف</button></>;
    if (noticeView === "submitted") return <><button className={styles.primaryButton} onClick={() => { const result = window.prompt("نتیجه را وارد کنید:", "برنده"); if (result) updateNotice(item.id, { stage: "results", result: result as Notice["result"] }); }}>ثبت نتیجه</button><button className={styles.secondaryButton}>ثبت پیگیری</button></>;
    return <button className={styles.secondaryButton} onClick={() => notify(item.result === "برنده" ? "پیش‌نویس قرارداد خودکار ساخته خواهد شد." : "فقط نتیجه برنده وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button>;
  }

  function directActions(item: DirectReferral) {
    if (directView === "all") return <>{item.stage === "new" ? <button className={styles.primaryButton} onClick={() => { updateDirect(item.id, { stage: "reviewing" }); notify("ارجاع مستقیم به فهرست پیشنهادی اضافه شد."); }}>افزودن به پیشنهادی</button> : <button className={styles.statusButton} disabled>{directLabel(item.stage)}</button>}<button className={styles.secondaryButton} onClick={() => setSelected({ title: item.title || "ارجاع مستقیم بدون عنوان", employer: item.employer || "کارفرما ثبت نشده", status: directLabel(item.stage), details: item.nextAction || item.description || "جزئیات تکمیلی ثبت نشده", deadline: item.targetDeadline || item.nextActionDue })}>مشاهده</button></>;
    if (directView === "recommended") return <><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "selected" })}>انتخاب</button><button className={styles.secondaryButton} onClick={() => updateDirect(item.id, { stage: "following_up" })}>پیگیری</button><button className={styles.dangerButton} onClick={() => updateDirect(item.id, { stage: "new" })}>حذف از پیشنهادی</button></>;
    if (directView === "selected") return <><button className={styles.secondaryButton} onClick={() => updateDirect(item.id, { stage: "preparing" })}>ثبت پیشرفت</button><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "submitted" })}>ارسال شد</button><button className={styles.dangerButton} onClick={() => updateDirect(item.id, { stage: "reviewing" })}>حذف از منتخب</button></>;
    if (directView === "submitted") return <><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "won", nextAction: "ایجاد پیش‌نویس قرارداد" })}>ثبت موفق</button><button className={styles.secondaryButton}>ثبت پیگیری</button></>;
    return <button className={styles.secondaryButton} onClick={() => notify(item.stage === "won" ? "پیش‌نویس قرارداد خودکار ساخته خواهد شد." : "فقط نتیجه موفق وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button>;
  }

  function LockHeader({ section, title }: { section: LockSection; title: string }) {
    return <div className={styles.lockedHeader}><div><h2>{title}</h2><span className={`${styles.lockBadge} ${editing[section] ? styles.editBadge : ""}`}>{editing[section] ? "در حال ویرایش" : "ثبت‌شده و قفل"}</span></div>{!editing[section] && <button className={styles.secondaryButton} onClick={() => setEditing((current) => ({ ...current, [section]: true }))}>ویرایش</button>}</div>;
  }

  function saveAndLock(section: LockSection) { setEditing((current) => ({ ...current, [section]: false })); notify(section === "schedule" ? "زمان‌بندی ذخیره و قفل شد." : "نسخه پیش‌نویس ذخیره و بخش دوباره قفل شد."); }

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}><div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1><p>مدیریت مناقصات، استعلامات و ارجاعات مستقیم همراه با تحلیل ChatGPT</p></div><Link href="/">بازگشت به سامانه</Link></header>
    <div className={styles.banner}><b>Preview تعاملی</b><span>شناسه Commit فقط در گزارش فنی نگهداری می‌شود و در رابط کاربری نمایش داده نمی‌شود.</span></div>
    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setSearch(""); setNoticeView("all"); setDirectView("all"); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article className={styles.kpi}><span>فراخوان جدید</span><b>{fa.format(24)}</b><small>از آخرین استخراج</small></article>
        <article className={styles.kpi}><span>تحلیل‌نشده</span><b>{fa.format(notices.filter((item) => item.score == null).length)}</b><small>در انتظار تحلیل</small></article>
        <article className={styles.kpi}><span>پیشنهادی</span><b>{fa.format(recommendedCount)}</b><small>نیازمند تصمیم انسانی</small></article>
        <article className={styles.kpi}><span>منتخب</span><b>{fa.format(selectedCount)}</b><small>پرونده در جریان</small></article>
        <article className={styles.kpi}><span>ارسال‌شده</span><b>{fa.format(submittedCount)}</b><small>در انتظار نتیجه</small></article>
        <article className={styles.kpi}><span>نزدیک مهلت</span><b>{fa.format(urgentCount)}</b><small>نیازمند اقدام فوری</small></article>
        <article className={styles.kpi}><span>ارجاع مستقیم فعال</span><b>{fa.format(direct.filter((item) => !["won", "lost", "stopped", "deferred"].includes(item.stage)).length)}</b><small>ثبت اولیه تا ارسال</small></article>
        <article className={styles.kpi}><span>نتیجه موفق</span><b>{fa.format(successCount)}</b><small>آماده پیش‌نویس قرارداد</small></article>
      </div>
      <div className={styles.dashboardGrid}>
        <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>۳ اقدام پیگیری عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>{fa.format(urgentCount)} پرونده نزدیک به مهلت</span><span>۱ پرونده ارسال‌شده بدون پیگیری نتیجه</span></div></article>
        <article className={styles.panel}><h2>قیف مدیریتی</h2><div className={styles.funnel}><span>استخراج و ثبت‌شده</span><span>پیشنهادی {fa.format(recommendedCount)}</span><span>منتخب {fa.format(selectedCount)}</span><span>ارسال‌شده {fa.format(submittedCount)}</span><span>نتیجه موفق {fa.format(successCount)}</span></div></article>
        <article className={styles.panel}><h2>برد و باخت</h2><div className={styles.outcomeGrid}><div><b>{fa.format(successCount)}</b><span>موفق</span></div><div><b>{fa.format(notices.filter((item) => item.result === "ناموفق").length + direct.filter((item) => item.stage === "lost").length)}</b><span>ناموفق</span></div><div><b>۶۷٪</b><span>نرخ موفقیت نمونه</span></div><div><b>{fa.format(successCount)}</b><span>پیش‌نویس قرارداد آینده</span></div></div></article>
        <article className={styles.panel}><h2>جمع‌بندی مدیریتی ChatGPT</h2><p>طرح جامع فارس بالاترین تناسب را دارد. استعلام نقشه‌برداری تهران فوریت زیادی دارد. ارجاع مستقیم پردیس اداری هنوز فقط ثبت اولیه شده و برای ورود به تحلیل باید به پیشنهادی اضافه شود.</p><div className={styles.summaryTags}><span>اقدام امروز: استعلام تهران</span><span>فرصت راهبردی: طرح جامع فارس</span><span>نیازمند تصمیم: پردیس اداری</span></div></article>
      </div>
      <article className={`${styles.panel} ${styles.activeCases}`}><div className={styles.sectionHeading}><div><span>انتهای داشبورد</span><h2>پرونده‌های فعال</h2></div><small>مناقصات، استعلامات و ارجاعات مستقیم منتخب یا ارسال‌شده</small></div><div className={styles.caseTable}>{activeCases.map((item) => { const u = urgency(item.deadline); return <button key={`${item.title}-${item.subtitle}`} onClick={() => setSelected({ title: item.title, employer: item.subtitle, status: item.stage, details: item.next, deadline: item.deadline })}><span><b>{item.title}</b><small>{item.subtitle}</small></span><span><b>{item.stage}</b><small>{item.next}</small></span><span className={`${styles.urgency} ${styles[u.tone]}`}><b>{u.label}</b><small>{u.remaining}</small></span></button>; })}</div></article>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section><div className={styles.sectionHeading}><div><span>فرآیند تصمیم‌گیری</span><h2>{tab === "tenders" ? "مناقصات" : "استعلامات"}</h2></div><small>در نمای «همه» می‌توانید هر رکورد را شخصاً به فهرست پیشنهادی اضافه کنید.</small></div><div className={styles.views}>{views.map(([id, label]) => <button key={id} className={noticeView === id ? styles.active : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div><div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی عنوان، کارفرما یا استان..." /><span>{fa.format(filteredNotices.length)} رکورد</span></div><div className={styles.recordList}>{filteredNotices.map((item) => { const u = urgency(item.deadline); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>{item.source} · {item.province}</small><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{u.remaining}</span><span>اولویت: {item.score == null ? "تحلیل نشده" : `${fa.format(item.score)} از ۱۰۰`}</span><span>پیشرفت: {fa.format(item.progress)}٪</span></div></div><div className={styles.decision}><span className={styles.stage}>{item.result || (item.stage === "submitted" ? "ارسال‌شده" : item.stage ? "منتخب" : item.recommended ? "پیشنهادی" : "فقط در همه")}</span><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div></dl><div className={styles.actions}>{noticeActions(item)}</div></div></article>; })}{!filteredNotices.length && <div className={styles.empty}>رکوردی در این نما وجود ندارد.</div>}</div></section>}

    {tab === "direct" && <section><div className={styles.sectionHeading}><div><span>فرآیند ارجاعات مستقیم</span><h2>ارجاعات مستقیم</h2></div><small>ثبت اولیه ابتدا فقط در «همه» قرار می‌گیرد؛ سپس با تصمیم شما وارد «پیشنهادی» می‌شود.</small></div>
      <form className={styles.directForm} onSubmit={registerDirect}>
        <div className={styles.formSection}><h3>اطلاعات پایه</h3><div className={styles.formGrid}><label>عنوان<input name="title" /></label><label>کارفرما<input name="employer" /></label><label>نوع ارجاع<select name="opportunityType" defaultValue="نیازمند تعیین"><option>نیازمند تعیین</option><option>مذاکره مستقیم</option><option>دعوت محدود</option><option>رایزنی با کارفرما</option><option>معرفی مستقیم</option><option>ترک تشریفات</option><option>سایر</option></select></label><label>حوزه تخصصی<input name="domain" /></label><label>استان<input name="province" /></label><label>شهر<input name="city" /></label><label>شماره یا کد مرجع<input name="referenceNumber" /></label><label>منبع یا نحوه شناسایی<input name="sourceText" /></label></div></div>
        <div className={styles.formSection}><h3>زمان، مبلغ و اقدام</h3><div className={styles.formGrid}><label>مهلت یا تاریخ هدف<input name="targetDeadline" type="datetime-local" /></label><label>مبلغ برآوردی ـ ریال<input name="estimatedValue" inputMode="numeric" /></label><label>احتمال تبدیل ـ درصد<input name="probability" type="number" min="0" max="100" /></label><label>مسئول<input name="responsible" /></label><label>اقدام بعدی<input name="nextAction" /></label><label>تاریخ اقدام بعدی<input name="nextActionDue" type="datetime-local" /></label><label>روش ارائه یا ارسال<input name="submissionMethod" /></label><label>محرمانگی<select name="confidentiality" defaultValue="داخلی"><option>عادی</option><option>داخلی</option><option>محرمانه</option></select></label></div></div>
        <div className={styles.formSection}><h3>اطلاعات رابط و توضیحات</h3><div className={styles.formGrid}><label>نام رابط<input name="contactName" /></label><label>تلفن رابط<input name="contactPhone" /></label><label>ایمیل رابط<input name="contactEmail" type="email" /></label><label className={styles.wideField}>شرح و یادداشت<textarea name="description" rows={4} /></label></div></div>
        <div className={styles.formActions}><small>همه فیلدها اختیاری‌اند؛ فقط اطلاعات تکمیل‌شده نمایش داده می‌شوند.</small><button className={styles.primaryButton}>ثبت در همه</button></div>
      </form>
      <div className={styles.views}>{views.map(([id, label]) => <button key={id} className={directView === id ? styles.active : ""} onClick={() => setDirectView(id)}>{label}</button>)}</div><div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی ارجاع مستقیم..." /><span>{fa.format(filteredDirect.length)} رکورد</span></div><div className={styles.recordList}>{filteredDirect.map((item) => { const u = urgency(item.targetDeadline || item.nextActionDue); const facts = [item.domain, item.province, item.city, item.referenceNumber ? `کد: ${item.referenceNumber}` : "", item.estimatedValue ? `برآورد: ${fa.format(Number(item.estimatedValue))} ریال` : "", item.probability != null ? `احتمال تبدیل: ${fa.format(item.probability)}٪` : "", u.remaining !== "نامشخص" ? u.remaining : ""].filter(Boolean); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>{item.opportunityType || "نوع نامشخص"} · {item.sourceText || "منبع ثبت نشده"}</small><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><h3>{item.title || "ارجاع مستقیم بدون عنوان"}</h3>{item.employer && <p>{item.employer}</p>}<div className={styles.facts}>{facts.map((fact) => <span key={fact}>{fact}</span>)}</div>{item.description && <p className={styles.description}>{item.description}</p>}</div><div className={styles.decision}><span className={styles.stage}>{directLabel(item.stage)}</span><dl>{item.responsible && <div><dt>مسئول</dt><dd>{item.responsible}</dd></div>}{item.nextAction && <div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div>}{item.contactName && <div><dt>رابط</dt><dd>{item.contactName}</dd></div>}{item.submissionMethod && <div><dt>روش ارسال</dt><dd>{item.submissionMethod}</dd></div>}</dl><div className={styles.actions}>{directActions(item)}</div></div></article>; })}{!filteredDirect.length && <div className={styles.empty}>رکوردی در این نما وجود ندارد.</div>}</div>
    </section>}

    {tab === "management" && <section><div className={styles.sectionHeading}><div><span>تنظیمات کنترل‌شده</span><h2>مدیریت زیرسامانه</h2></div><small>اطلاعات پس از ذخیره قفل می‌شوند و برای اصلاح باید وارد حالت ویرایش شوید.</small></div><div className={styles.managementTabs}>{managementTabs.map(([id, label]) => <button key={id} className={managementView === id ? styles.active : ""} onClick={() => setManagementView(id)}>{label}</button>)}</div>
      {managementView === "extraction" && <div className={styles.managementGrid}><article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.alertList}><span>هزاره — فعال</span><span>پارس نماد داده — فعال</span><span>ستاد ایران — موقتاً تعلیق‌شده / نیازمند بررسی مجدد در ساعت دسترسی</span></div><button className={styles.primaryButton} onClick={() => notify("استخراج Preview آغاز شد؛ محیط واقعی تغییر نمی‌کند.")}>شروع استخراج انتخاب‌شده</button></article><article className={styles.lockedCard}><LockHeader section="schedule" title="زمان‌بندی استخراج و تحلیل" /><div className={styles.scheduleGrid}><label>وضعیت<select disabled={!editing.schedule} value={schedule.enabled ? "enabled" : "disabled"} onChange={(event) => setSchedule((current) => ({ ...current, enabled: event.target.value === "enabled" }))}><option value="disabled">غیرفعال</option><option value="enabled">فعال</option></select></label><label>نوع برنامه<select disabled={!editing.schedule} value={schedule.cadence} onChange={(event) => setSchedule((current) => ({ ...current, cadence: event.target.value }))}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label><label>ساعت روزانه<input disabled={!editing.schedule || schedule.cadence !== "daily"} type="time" value={schedule.dailyTime} onChange={(event) => setSchedule((current) => ({ ...current, dailyTime: event.target.value }))} /></label><label>فاصله ساعتی ـ دقیقه<input disabled={!editing.schedule || schedule.cadence !== "hourly"} type="number" min="60" value={schedule.intervalMinutes} onChange={(event) => setSchedule((current) => ({ ...current, intervalMinutes: Number(event.target.value) }))} /></label><label>تأخیر تحلیل ـ دقیقه<input disabled={!editing.schedule} type="number" min="0" value={schedule.delayMinutes} onChange={(event) => setSchedule((current) => ({ ...current, delayMinutes: Number(event.target.value) }))} /></label><label>منطقه زمانی<select disabled={!editing.schedule} value={schedule.timezone} onChange={(event) => setSchedule((current) => ({ ...current, timezone: event.target.value }))}><option>Asia/Tehran</option><option>Asia/Baku</option></select></label></div>{editing.schedule && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setEditing((current) => ({ ...current, schedule: false }))}>انصراف</button><button className={styles.primaryButton} onClick={() => saveAndLock("schedule")}>ذخیره و قفل</button></div>}</article></div>}
      {managementView === "prompts" && <article className={styles.lockedCard}><LockHeader section="prompts" title="نقش و Prompt تحلیل واحد" /><div className={styles.fields}><label>نقش تخصصی<textarea disabled={!editing.prompts} rows={4} value={context.role} onChange={(event) => setContext((current) => ({ ...current, role: event.target.value }))} /></label><label>دستورهای پایه<textarea disabled={!editing.prompts} rows={5} value={context.base} onChange={(event) => setContext((current) => ({ ...current, base: event.target.value }))} /></label><label>Prompt واحد مناقصات و استعلامات<textarea disabled={!editing.prompts} rows={8} value={context.prompt} onChange={(event) => setContext((current) => ({ ...current, prompt: event.target.value }))} /></label><label className={styles.fileBox}>بارگذاری فایل مرجع<input disabled={!editing.prompts} type="file" multiple onChange={(event) => handleContextFile("prompt", event)} /><small>{uploadedFiles.prompt.join("، ") || "فایلی انتخاب نشده"}</small></label></div>{editing.prompts && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setEditing((current) => ({ ...current, prompts: false }))}>انصراف</button><button className={styles.primaryButton} onClick={() => saveAndLock("prompts")}>ذخیره نسخه و قفل</button></div>}</article>}
      {managementView === "keywords" && <article className={styles.lockedCard}><LockHeader section="keywords" title="کلیدواژه‌ها" /><div className={styles.fields}><label>کلیدواژه‌های فعال<textarea disabled={!editing.keywords} rows={10} value={context.activeKeywords} onChange={(event) => setContext((current) => ({ ...current, activeKeywords: event.target.value }))} /></label><label>کلیدواژه‌های حذف یا احتیاط<textarea disabled={!editing.keywords} rows={7} value={context.excludedKeywords} onChange={(event) => setContext((current) => ({ ...current, excludedKeywords: event.target.value }))} /></label><label className={styles.fileBox}>بارگذاری فایل کلیدواژه<input disabled={!editing.keywords} type="file" multiple onChange={(event) => handleContextFile("keywords", event)} /><small>{uploadedFiles.keywords.join("، ") || "txt، csv یا xlsx"}</small></label></div>{editing.keywords && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setEditing((current) => ({ ...current, keywords: false }))}>انصراف</button><button className={styles.primaryButton} onClick={() => saveAndLock("keywords")}>ذخیره نسخه و قفل</button></div>}</article>}
      {managementView === "company" && <article className={styles.lockedCard}><LockHeader section="company" title="پروفایل، صلاحیت‌ها و رزومه" /><div className={styles.fields}><label>پروفایل خلاصه شرکت<textarea disabled={!editing.company} rows={6} value={context.companyProfile} onChange={(event) => setContext((current) => ({ ...current, companyProfile: event.target.value }))} /></label><label>صلاحیت‌ها<textarea disabled={!editing.company} rows={7} value={context.qualifications} onChange={(event) => setContext((current) => ({ ...current, qualifications: event.target.value }))} /></label><label>سوابق و تجربیات<textarea disabled={!editing.company} rows={8} value={context.experience} onChange={(event) => setContext((current) => ({ ...current, experience: event.target.value }))} /></label><label className={styles.fileBox}>بارگذاری پروفایل یا رزومه<input disabled={!editing.company} type="file" multiple onChange={(event) => handleContextFile("resume", event)} /><small>{uploadedFiles.resume.join("، ") || "pdf، docx، txt یا md"}</small></label></div>{editing.company && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setEditing((current) => ({ ...current, company: false }))}>انصراف</button><button className={styles.primaryButton} onClick={() => saveAndLock("company")}>ذخیره نسخه و قفل</button></div>}</article>}
      {managementView === "versions" && <div className={styles.managementGrid}><article className={styles.panel}><h2>نسخه فعال</h2><dl><div><dt>نسخه</dt><dd>۱۲</dd></div><div><dt>وضعیت</dt><dd>فعال و قفل</dd></div><div><dt>فرمان دستی</dt><dd>PDP</dd></div></dl></article><article className={styles.panel}><h2>پیش‌نویس‌ها</h2><p>هر ذخیره در بخش‌های نقش، کلیدواژه یا پروفایل یک Snapshot پیش‌نویس می‌سازد. فعال‌سازی نهایی فقط با تأیید مدیر انجام می‌شود.</p><button className={styles.primaryButton} onClick={() => notify("نسخه پیش‌نویس فعال شد؛ نسخه قبلی بازنشسته شد.")}>فعال‌سازی آخرین پیش‌نویس</button></article></div>}
    </section>}

    {selected && <div className={styles.backdrop} onMouseDown={() => setSelected(null)}><section className={styles.modal} onMouseDown={(event) => event.stopPropagation()}><header><div><small>{selected.status}</small><h2>{selected.title}</h2><p>{selected.employer}</p></div><button onClick={() => setSelected(null)}>×</button></header><div className={styles.modalBody}><dl><div><dt>وضعیت</dt><dd>{selected.status}</dd></div><div><dt>مهلت</dt><dd>{selected.deadline ? faDate.format(new Date(selected.deadline)) : "تعیین نشده"}</dd></div><div><dt>جزئیات</dt><dd>{selected.details}</dd></div></dl></div></section></div>}
  </main>;
}
