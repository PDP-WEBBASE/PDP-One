"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import styles from "./workspace-v3.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type View = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "prompt" | "keywords" | "company" | "versions";
type LockKey = "schedule" | "prompt" | "keywords" | "company";

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
  responsible: string;
  nextAction: string;
  score: number | null;
};

type DirectReferral = {
  id: string;
  title: string;
  employer: string;
  province: string;
  stage: "new" | "reviewing" | "selected" | "preparing" | "submitted" | "won" | "lost" | "stopped";
  responsible: string;
  nextAction: string;
  due: string | null;
  probability: number;
};

type Schedule = {
  enabled: boolean;
  cadence: "hourly" | "daily";
  interval: number;
  dailyTime: string;
  delay: number;
  timezone: string;
};

type Editor = {
  role: string;
  base: string;
  prompt: string;
  activeKeywords: string;
  excludedKeywords: string;
  profile: string;
  qualifications: string;
  experience: string;
};

const fa = new Intl.NumberFormat("fa-IR");
const seedNotices: Notice[] = [
  { id: "T1", kind: "tender", title: "خدمات مشاوره طراحی و نظارت مجموعه اداری", employer: "شرکت توسعه عمران", province: "تهران", source: "هزاره", deadline: "2026-07-25T16:00:00+03:30", recommended: true, stage: "selected", result: "", responsible: "محمد ملکی", nextAction: "تقسیم کار تهیه پیشنهاد", score: 91 },
  { id: "T2", kind: "tender", title: "مطالعات طرح جامع و برنامه‌ریزی فضایی", employer: "اداره کل راه و شهرسازی", province: "فارس", source: "پارس نماد داده", deadline: "2026-07-30T14:00:00+03:30", recommended: true, stage: "preparing", result: "", responsible: "کارشناس مناقصات", nextAction: "تهیه ساختار شکست خدمات", score: 95 },
  { id: "T3", kind: "tender", title: "طراحی تأسیسات بیمارستان", employer: "دانشگاه علوم پزشکی", province: "البرز", source: "هزاره", deadline: "2026-07-27T12:00:00+03:30", recommended: false, stage: "", result: "", responsible: "", nextAction: "بررسی اولیه", score: null },
  { id: "T4", kind: "tender", title: "مطالعات امکان‌سنجی شهرک صنعتی", employer: "شرکت شهرک‌های صنعتی", province: "آذربایجان شرقی", source: "پارس نماد داده", deadline: "2026-07-22T15:00:00+03:30", recommended: true, stage: "submitted", result: "", responsible: "توسعه کسب‌وکار", nextAction: "پیگیری نتیجه", score: 82 },
  { id: "T5", kind: "tender", title: "طراحی معماری مجتمع آموزشی", employer: "سازمان نوسازی مدارس", province: "قم", source: "هزاره", deadline: "2026-07-10T12:00:00+03:30", recommended: true, stage: "results", result: "برنده", responsible: "مدیرعامل", nextAction: "ایجاد پیش‌نویس قرارداد", score: 94 },
  { id: "I1", kind: "inquiry", title: "استعلام خدمات نقشه‌برداری", employer: "شهرداری منطقه", province: "تهران", source: "پارس نماد داده", deadline: "2026-07-23T13:00:00+03:30", recommended: true, stage: "selected", result: "", responsible: "کارشناس مناقصات", nextAction: "دریافت قیمت و تأیید مدیر", score: 88 },
  { id: "I2", kind: "inquiry", title: "استعلام گزارش توجیهی و امکان‌سنجی", employer: "منطقه ویژه اقتصادی", province: "بوشهر", source: "هزاره", deadline: "2026-07-26T15:00:00+03:30", recommended: true, stage: "preparing", result: "", responsible: "واحد مطالعات", nextAction: "جلسه با کارشناس مالی", score: 86 },
  { id: "I3", kind: "inquiry", title: "استعلام طراحی روشنایی محوطه صنعتی", employer: "شرکت تولیدی نمونه", province: "قزوین", source: "پارس نماد داده", deadline: "2026-07-24T10:00:00+03:30", recommended: false, stage: "", result: "", responsible: "", nextAction: "دریافت پیوست فنی", score: null },
  { id: "I4", kind: "inquiry", title: "استعلام بازنگری نقشه‌های معماری", employer: "شرکت عمران و مسکن", province: "مازندران", source: "هزاره", deadline: "2026-07-18T12:00:00+03:30", recommended: true, stage: "results", result: "ناموفق", responsible: "واحد فنی", nextAction: "مرور علت باخت", score: 79 },
];

const seedDirect: DirectReferral[] = [
  { id: "D1", title: "رایزنی طرح توسعه پردیس اداری", employer: "گروه سرمایه‌گذاری پارس", province: "تهران", stage: "reviewing", responsible: "محمد ملکی", nextAction: "ارسال معرفی‌نامه سوابق", due: "2026-07-23T11:00:00+03:30", probability: 70 },
  { id: "D2", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی نو", province: "یزد", stage: "selected", responsible: "توسعه کسب‌وکار", nextAction: "هماهنگی جلسه فنی", due: "2026-07-25T10:00:00+03:30", probability: 55 },
  { id: "D3", title: "دعوت محدود طراحی مجموعه درمانی", employer: "بنیاد توسعه سلامت", province: "تهران", stage: "submitted", responsible: "مدیر فنی", nextAction: "پیگیری دریافت پیشنهاد", due: "2026-07-24T09:00:00+03:30", probability: 80 },
  { id: "D4", title: "طراحی مرکز خدمات شهری", employer: "شرکت عمران شهری", province: "البرز", stage: "won", responsible: "مدیرعامل", nextAction: "ایجاد پیش‌نویس قرارداد", due: "2026-07-26T10:00:00+03:30", probability: 100 },
];

const initialEditor: Editor = {
  role: "تحلیلگر ارشد مناقصات، استعلامات و ارجاعات مستقیم شرکت مهندسین مشاور طرح و برنامه پارس",
  base: "تحلیل بر اساس صلاحیت، ظرفیت، زمان، ریسک و سوابق انجام شود و نتیجه فقط پیش‌نویس باشد.",
  prompt: "هر فرصت را از نظر تناسب با شرکت، زمان باقی‌مانده، شرایط، ریسک، سوابق مرتبط، ظرفیت پاسخ و اقدام پیشنهادی تحلیل کن.",
  activeKeywords: "طراحی معماری\nنظارت\nطرح جامع\nامکان‌سنجی\nتأسیسات",
  excludedKeywords: "تأمین کالا\nاجرای صرف\nخرید تجهیزات",
  profile: "شرکت مهندسین مشاور طرح و برنامه پارس؛ فعال در معماری، شهرسازی، تأسیسات و برنامه‌ریزی فضایی.",
  qualifications: "رتبه ۳ معماری\nرتبه ۳ شهرسازی\nرتبه ۳ تأسیسات برق و مکانیک\nمطالعات جغرافیایی و برنامه‌ریزی فضایی",
  experience: "پروژه‌های اداری و آموزشی\nمطالعات شهری و منطقه‌ای\nمطالعات امکان‌سنجی",
};

const tabs: [Tab, string][] = [["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"], ["direct", "ارجاعات مستقیم"], ["management", "مدیریت زیرسامانه"]];
const views: [View, string][] = [["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"], ["submitted", "ارسال‌شده"], ["results", "نتایج"]];
const managementTabs: [ManagementView, string][] = [["extraction", "استخراج و منابع"], ["prompt", "نقش و Prompt"], ["keywords", "کلیدواژه‌ها"], ["company", "پروفایل، صلاحیت و رزومه"], ["versions", "نسخه‌ها و فعال‌سازی"]];

function urgency(value: string | null) {
  if (!value) return { label: "نامشخص", remaining: "زمان نامشخص", tone: "unknown" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { label: "مهلت گذشته", remaining: `${fa.format(Math.abs(hours))} ساعت گذشته`, tone: "critical" };
  if (hours < 24) return { label: "فوریت بحرانی", remaining: `${fa.format(hours)} ساعت باقی‌مانده`, tone: "critical" };
  if (hours <= 72) return { label: "فوریت زیاد", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "high" };
  if (hours <= 168) return { label: "فوریت متوسط", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "medium" };
  return { label: "عادی", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "normal" };
}

function noticeMatches(item: Notice, view: View) {
  if (view === "all") return true;
  if (view === "recommended") return item.recommended && !item.stage;
  if (view === "selected") return ["selected", "preparing"].includes(item.stage);
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "results";
}

function directMatches(item: DirectReferral, view: View) {
  if (view === "all") return true;
  if (view === "recommended") return ["new", "reviewing"].includes(item.stage);
  if (view === "selected") return ["selected", "preparing"].includes(item.stage);
  if (view === "submitted") return item.stage === "submitted";
  return ["won", "lost", "stopped"].includes(item.stage);
}

export default function ProcurementWorkspaceV3() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [view, setView] = useState<View>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [notices, setNotices] = useState(seedNotices);
  const [direct, setDirect] = useState(seedDirect);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<{ title: string; employer: string; status: string; next: string; deadline: string | null } | null>(null);
  const [editing, setEditing] = useState<Record<LockKey, boolean>>({ schedule: false, prompt: false, keywords: false, company: false });
  const [editor, setEditor] = useState(initialEditor);
  const [savedEditor, setSavedEditor] = useState(initialEditor);
  const [files, setFiles] = useState<Record<string, string[]>>({ prompt: [], keywords: [], profile: [], qualifications: [], resume: [] });
  const [schedule, setSchedule] = useState<Schedule>({ enabled: false, cadence: "daily", interval: 60, dailyTime: "17:00", delay: 60, timezone: "Asia/Tehran" });
  const [savedSchedule, setSavedSchedule] = useState(schedule);
  const [versions, setVersions] = useState([{ version: 12, status: "فعال" }, { version: 11, status: "بازنشسته" }]);

  const stats = useMemo(() => {
    const tender = notices.filter((item) => item.kind === "tender");
    const inquiry = notices.filter((item) => item.kind === "inquiry");
    const noticeRow = (label: string, items: Notice[]) => ({
      label,
      total: items.length,
      participating: items.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).length,
      won: items.filter((item) => item.result === "برنده").length,
    });
    return [
      noticeRow("مناقصات", tender),
      noticeRow("استعلامات", inquiry),
      { label: "ارجاعات مستقیم", total: direct.length, participating: direct.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).length, won: direct.filter((item) => item.stage === "won").length },
    ].map((item) => ({ ...item, participationRate: Math.round(item.participating / Math.max(item.total, 1) * 100), winRate: Math.round(item.won / Math.max(item.participating + item.won, 1) * 100) }));
  }, [direct, notices]);

  const filteredNotices = notices.filter((item) => (tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry") && noticeMatches(item, view) && (!search || `${item.title} ${item.employer} ${item.province}`.includes(search)));
  const filteredDirect = direct.filter((item) => directMatches(item, view) && (!search || `${item.title} ${item.employer} ${item.province}`.includes(search)));
  const maxTotal = Math.max(...stats.map((item) => item.total), 1);
  const participatingTotal = stats.reduce((sum, item) => sum + item.participating, 0);
  const wonTotal = stats.reduce((sum, item) => sum + item.won, 0);
  const total = stats.reduce((sum, item) => sum + item.total, 0);
  const donutTotal = Math.max(participatingTotal, 1);
  const first = stats[0].participating / donutTotal * 100;
  const second = stats[1].participating / donutTotal * 100;
  const donut = `conic-gradient(#236b78 0 ${first}%, #d2a42e ${first}% ${first + second}%, #8b70a7 ${first + second}% 100%)`;

  function notify(text: string) { setMessage(text); window.setTimeout(() => setMessage(""), 4000); }
  function updateNotice(id: string, change: Partial<Notice>) { setNotices((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }
  function updateDirect(id: string, change: Partial<DirectReferral>) { setDirect((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }
  function statusOfNotice(item: Notice) { return item.result || (item.stage === "submitted" ? "ارسال‌شده" : item.stage ? "منتخب" : item.recommended ? "پیشنهادی" : "ثبت‌شده"); }
  function statusOfDirect(item: DirectReferral) { return ({ new: "پیشنهادی", reviewing: "پیشنهادی", selected: "منتخب", preparing: "منتخب · در دست تهیه", submitted: "ارسال‌شده", won: "موفق", lost: "ناموفق", stopped: "متوقف‌شده" } as Record<string, string>)[item.stage]; }

  function noticeActions(item: Notice) {
    if (view === "all") return <><button className={styles.secondary} onClick={() => setSelected({ title: item.title, employer: item.employer, status: statusOfNotice(item), next: item.nextAction, deadline: item.deadline })}>مشاهده</button>{!item.recommended && !item.stage && <button className={styles.primary} onClick={() => { updateNotice(item.id, { recommended: true }); notify("به فهرست پیشنهادی اضافه شد."); }}>افزودن به پیشنهادی</button>}</>;
    if (view === "recommended") return <><button className={styles.primary} onClick={() => updateNotice(item.id, { stage: "selected", responsible: item.responsible || "محمد ملکی", nextAction: "تعیین برنامه تهیه پیشنهاد" })}>انتخاب</button><button className={styles.danger} onClick={() => updateNotice(item.id, { recommended: false })}>حذف</button></>;
    if (view === "selected") return <><button className={styles.secondary} onClick={() => updateNotice(item.id, { stage: "preparing" })}>ثبت پیشرفت</button><button className={styles.primary} onClick={() => updateNotice(item.id, { stage: "submitted", nextAction: "پیگیری نتیجه" })}>ارسال شد</button><button className={styles.danger} onClick={() => updateNotice(item.id, { stage: "", recommended: true })}>حذف</button></>;
    if (view === "submitted") return <><button className={styles.primary} onClick={() => { const result = window.prompt("نتیجه:", "برنده"); if (result) updateNotice(item.id, { stage: "results", result: result as Notice["result"], nextAction: result === "برنده" ? "ایجاد پیش‌نویس قرارداد" : "ثبت علت نتیجه" }); }}>ثبت نتیجه</button><button className={styles.secondary}>پیگیری</button></>;
    return <button className={styles.secondary} onClick={() => notify(item.result === "برنده" ? "پیش‌نویس قرارداد در ماژول قراردادها خودکار ساخته خواهد شد." : "فقط نتیجه برنده وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button>;
  }

  function directActions(item: DirectReferral) {
    if (view === "all") return <button className={styles.secondary} onClick={() => setSelected({ title: item.title, employer: item.employer, status: statusOfDirect(item), next: item.nextAction, deadline: item.due })}>مشاهده</button>;
    if (view === "recommended") return <><button className={styles.primary} onClick={() => updateDirect(item.id, { stage: "selected" })}>انتخاب</button><button className={styles.danger} onClick={() => setDirect((items) => items.filter((current) => current.id !== item.id))}>حذف</button></>;
    if (view === "selected") return <><button className={styles.secondary} onClick={() => updateDirect(item.id, { stage: "preparing" })}>ثبت پیشرفت</button><button className={styles.primary} onClick={() => updateDirect(item.id, { stage: "submitted" })}>ارسال شد</button><button className={styles.danger} onClick={() => updateDirect(item.id, { stage: "reviewing" })}>حذف</button></>;
    if (view === "submitted") return <><button className={styles.primary} onClick={() => updateDirect(item.id, { stage: "won", nextAction: "ایجاد پیش‌نویس قرارداد" })}>ثبت موفق</button><button className={styles.secondary}>پیگیری</button></>;
    return <button className={styles.secondary} onClick={() => notify(item.stage === "won" ? "پیش‌نویس قرارداد در ماژول قراردادها خودکار ساخته خواهد شد." : "فقط نتیجه موفق وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button>;
  }

  async function loadText(event: ChangeEvent<HTMLInputElement>, key: keyof Editor, fileKey: string) {
    const selectedFiles = Array.from(event.target.files || []);
    setFiles((current) => ({ ...current, [fileKey]: [...current[fileKey], ...selectedFiles.map((file) => file.name)] }));
    const text = selectedFiles.find((file) => /\.(txt|md)$/i.test(file.name));
    if (text) setEditor((current) => ({ ...current, [key]: await text.text() }));
  }

  function lockHeader(key: LockKey, title: string) {
    const open = editing[key];
    return <div className={styles.lockHeader}><div><h2>{title}</h2><span className={open ? styles.editingBadge : styles.lockedBadge}>{open ? "در حال ویرایش" : "ثبت‌شده و قفل"}</span></div>{!open && <button className={styles.secondary} onClick={() => setEditing((current) => ({ ...current, [key]: true }))}>ویرایش</button>}</div>;
  }

  function saveSection(key: LockKey) {
    setSavedEditor(editor);
    const next = Math.max(...versions.map((item) => item.version)) + 1;
    setVersions((items) => [{ version: next, status: "پیش‌نویس" }, ...items]);
    setEditing((current) => ({ ...current, [key]: false }));
    notify(`نسخه پیش‌نویس ${fa.format(next)} ذخیره و بخش دوباره قفل شد.`);
  }

  function cancelSection(key: LockKey) {
    setEditor(savedEditor);
    setEditing((current) => ({ ...current, [key]: false }));
  }

  function renderRecord(item: Notice) {
    const u = urgency(item.deadline);
    return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>{item.source} · {item.province}</small><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{u.remaining}</span><span>امتیاز: {item.score ?? "تحلیل نشده"}</span><span>مسئول: {item.responsible || "تعیین نشده"}</span></div></div><div className={styles.decision}><b>{statusOfNotice(item)}</b><small>{item.nextAction}</small><div className={styles.actions}>{noticeActions(item)}</div></div></article>;
  }

  function renderDirect(item: DirectReferral) {
    const u = urgency(item.due);
    return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>ارجاع مستقیم · {item.province}</small><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{u.remaining}</span><span>احتمال تبدیل: {fa.format(item.probability)}٪</span><span>مسئول: {item.responsible}</span></div></div><div className={styles.decision}><b>{statusOfDirect(item)}</b><small>{item.nextAction}</small><div className={styles.actions}>{directActions(item)}</div></div></article>;
  }

  function createDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setDirect((items) => [{ id: `D-${Date.now()}`, title: String(form.get("title")), employer: String(form.get("employer")), province: "تعیین نشده", stage: "new", responsible: "ثبت‌کننده", nextAction: String(form.get("action")), due: new Date(Date.now() + 86400000).toISOString(), probability: 20 }, ...items]);
    event.currentTarget.reset();
    notify("ارجاع مستقیم در فهرست پیشنهادی ثبت شد.");
  }

  const activeCases = [
    ...notices.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title, type: item.kind === "tender" ? "مناقصه" : "استعلام", employer: item.employer, status: statusOfNotice(item), next: item.nextAction, date: item.deadline })),
    ...direct.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title, type: "ارجاع مستقیم", employer: item.employer, status: statusOfDirect(item), next: item.nextAction, date: item.due })),
  ];

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}><div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1><p>مدیریت مناقصات، استعلامات و ارجاعات مستقیم همراه با تحلیل ChatGPT</p></div><Link href="/">بازگشت به سامانه</Link></header>
    <div className={styles.banner}><b>Preview تعاملی نسخه جدید</b><span>داده‌ها نمونه‌اند و محیط واقعی تغییر نمی‌کند.</span></div>
    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setView("all"); setSearch(""); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article><span>کل استخراج و ثبت</span><b>{fa.format(total)}</b><small>مجموع سه مسیر</small></article>
        <article><span>در حال شرکت</span><b>{fa.format(participatingTotal)}</b><small>منتخب و ارسال‌شده</small></article>
        <article><span>برنده یا موفق</span><b>{fa.format(wonTotal)}</b><small>آماده پیش‌نویس قرارداد</small></article>
        <article><span>نرخ مشارکت</span><b>{fa.format(Math.round(participatingTotal / Math.max(total, 1) * 100))}٪</b><small>شرکت نسبت به کل</small></article>
        <article><span>نرخ موفقیت</span><b>{fa.format(Math.round(wonTotal / Math.max(participatingTotal + wonTotal, 1) * 100))}٪</b><small>برد نسبت به مشارکت</small></article>
        <article><span>فوریت زیاد</span><b>{fa.format(notices.filter((item) => ["critical", "high"].includes(urgency(item.deadline).tone) && item.stage !== "results").length)}</b><small>نیازمند اقدام</small></article>
      </div>
      <div className={styles.chartGrid}>
        <article className={styles.panel}><h2>مقایسه مسیرها</h2><div className={styles.legend}><span><i className={styles.totalDot}/>استخراج/ثبت‌شده</span><span><i className={styles.participatingDot}/>در حال شرکت</span><span><i className={styles.wonDot}/>برنده/موفق</span></div><div className={styles.barChart}>{stats.map((item) => <div className={styles.barGroup} key={item.label}><span>{item.label}</span><div className={styles.bars}><div className={`${styles.bar} ${styles.totalBar}`} style={{ height: `${Math.max(item.total / maxTotal * 100, 8)}%` }}><b>{fa.format(item.total)}</b></div><div className={`${styles.bar} ${styles.participatingBar}`} style={{ height: `${Math.max(item.participating / maxTotal * 100, 5)}%` }}><b>{fa.format(item.participating)}</b></div><div className={`${styles.bar} ${styles.wonBar}`} style={{ height: `${Math.max(item.won / maxTotal * 100, 3)}%` }}><b>{fa.format(item.won)}</b></div></div><small>مشارکت {fa.format(item.participationRate)}٪ · موفقیت {fa.format(item.winRate)}٪</small></div>)}</div></article>
        <article className={styles.panel}><h2>ترکیب پرونده‌های در حال شرکت</h2><div className={styles.donutWrap}><div className={styles.donut} style={{ background: donut }}><div><b>{fa.format(participatingTotal)}</b><small>پرونده</small></div></div><div className={styles.donutLegend}>{stats.map((item, index) => <p key={item.label}><i style={{ background: ["#236b78", "#d2a42e", "#8b70a7"][index] }}/><span>{item.label}</span><b>{fa.format(item.participating)}</b></p>)}</div></div></article>
      </div>
      <div className={styles.summaryGrid}>
        <article className={styles.panel}><h2>نرخ تبدیل هر مسیر</h2>{stats.map((item) => <div className={styles.rateRow} key={item.label}><span>{item.label}</span><div><i style={{ width: `${item.participationRate}%` }}/></div><b>{fa.format(item.participationRate)}٪ مشارکت</b></div>)}</article>
        <article className={styles.panel}><h2>گزارش‌های پیشنهادی بعدی</h2><ul><li>مقایسه عملکرد منابع هزاره و پارس نماد</li><li>تفکیک فرصت‌ها بر اساس حوزه تخصصی، استان و کارفرما</li><li>روند ماهانه و مقایسه با دوره مشابه سال قبل</li><li>میانگین زمان از پیشنهاد تا ارسال و نتیجه</li><li>دلایل برد، باخت و حذف از فرایند</li></ul></article>
      </div>
      <article className={`${styles.panel} ${styles.activeCases}`}><h2>پرونده‌های فعال</h2><div className={styles.caseTable}>{activeCases.map((item) => { const u = urgency(item.date); return <button key={`${item.type}-${item.title}`} onClick={() => setSelected({ title: item.title, employer: item.employer, status: item.status, next: item.next, deadline: item.date })}><span><b>{item.title}</b><small>{item.type} · {item.employer}</small></span><span><b>{item.status}</b><small>{item.next}</small></span><span className={`${styles.urgency} ${styles[u.tone]}`}>{u.remaining}</span></button>; })}</div></article>
    </section>}

    {(tab === "tenders" || tab === "inquiries" || tab === "direct") && <section>
      <div className={styles.sectionHeading}><div><span>فرآیند تصمیم‌گیری</span><h2>{tab === "tenders" ? "مناقصات" : tab === "inquiries" ? "استعلامات" : "ارجاعات مستقیم"}</h2></div><small>همه → پیشنهادی → منتخب → ارسال‌شده → نتایج</small></div>
      {tab === "direct" && <form className={styles.quickForm} onSubmit={createDirect}><label>عنوان<input name="title" required/></label><label>کارفرما<input name="employer" required/></label><label>اقدام بعدی<input name="action" required/></label><button>ثبت در پیشنهادی</button></form>}
      <div className={styles.views}>{views.map(([id, label]) => <button key={id} className={view === id ? styles.active : ""} onClick={() => setView(id)}>{label}</button>)}</div>
      <div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما یا استان..."/><span>{fa.format(tab === "direct" ? filteredDirect.length : filteredNotices.length)} رکورد</span></div>
      <div className={styles.recordList}>{tab === "direct" ? filteredDirect.map(renderDirect) : filteredNotices.map(renderRecord)}</div>
    </section>}

    {tab === "management" && <section>
      <div className={styles.sectionHeading}><div><span>تنظیمات کنترل‌شده</span><h2>مدیریت زیرسامانه</h2></div><small>اطلاعات پس از ثبت قفل می‌شوند و فقط با «ویرایش» قابل تغییرند.</small></div>
      <div className={styles.managementTabs}>{managementTabs.map(([id, label]) => <button key={id} className={managementView === id ? styles.active : ""} onClick={() => setManagementView(id)}>{label}</button>)}</div>

      {managementView === "extraction" && <div className={styles.managementGrid}>
        <article className={styles.panel}><h2>منابع استخراج</h2><label className={styles.check}><input type="checkbox" defaultChecked/>هزاره</label><label className={styles.check}><input type="checkbox" defaultChecked/>پارس نماد داده</label><label className={styles.check}><input type="checkbox"/>ستاد ایران — موقتاً تعلیق‌شده</label><button className={styles.primary} onClick={() => notify("استخراج نمایشی آغاز شد.")}>شروع استخراج انتخاب‌شده‌ها</button></article>
        <article className={styles.lockedCard}>{lockHeader("schedule", "زمان‌بندی استخراج و تحلیل")}<div className={styles.scheduleGrid}><label>فعال<input type="checkbox" checked={schedule.enabled} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, enabled: event.target.checked })}/></label><label>نوع برنامه<select value={schedule.cadence} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, cadence: event.target.value as Schedule["cadence"] })}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label>{schedule.cadence === "daily" ? <label>ساعت روزانه<input type="time" value={schedule.dailyTime} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, dailyTime: event.target.value })}/></label> : <label>فاصله اجرا<input type="number" min="60" value={schedule.interval} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, interval: Number(event.target.value) })}/></label>}<label>تأخیر تحلیل ChatGPT<input type="number" min="0" value={schedule.delay} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, delay: Number(event.target.value) })}/></label><label>منطقه زمانی<select value={schedule.timezone} disabled={!editing.schedule} onChange={(event) => setSchedule({ ...schedule, timezone: event.target.value })}><option value="Asia/Tehran">Asia/Tehran</option><option value="Asia/Baku">Asia/Baku</option></select></label></div>{editing.schedule && <div className={styles.editorActions}><button className={styles.secondary} onClick={() => { setSchedule(savedSchedule); setEditing({ ...editing, schedule: false }); }}>انصراف</button><button className={styles.primary} onClick={() => { setSavedSchedule(schedule); setEditing({ ...editing, schedule: false }); notify("زمان‌بندی ذخیره و قفل شد."); }}>ذخیره و قفل</button></div>}</article>
      </div>}

      {managementView === "prompt" && <article className={styles.lockedCard}>{lockHeader("prompt", "نقش و Prompt تحلیل واحد")}<div className={styles.fields}><label>نقش تخصصی<textarea rows={4} disabled={!editing.prompt} value={editor.role} onChange={(event) => setEditor({ ...editor, role: event.target.value })}/></label><label>قواعد پایه<textarea rows={5} disabled={!editing.prompt} value={editor.base} onChange={(event) => setEditor({ ...editor, base: event.target.value })}/></label><label>Prompt واحد تحلیل مناقصات و استعلامات<textarea rows={9} disabled={!editing.prompt} value={editor.prompt} onChange={(event) => setEditor({ ...editor, prompt: event.target.value })}/></label><label className={styles.fileBox}>بارگذاری فایل مرجع Prompt<input type="file" disabled={!editing.prompt} accept=".txt,.md,.pdf,.docx" onChange={(event) => loadText(event, "prompt", "prompt")}/><small>{files.prompt.join("، ") || "فایلی انتخاب نشده است."}</small></label></div>{editing.prompt && <div className={styles.editorActions}><button className={styles.secondary} onClick={() => cancelSection("prompt")}>انصراف</button><button className={styles.primary} onClick={() => saveSection("prompt")}>ذخیره نسخه و قفل</button></div>}</article>}

      {managementView === "keywords" && <article className={styles.lockedCard}>{lockHeader("keywords", "کلیدواژه‌ها")}<div className={styles.fields}><label>کلیدواژه‌های فعال<textarea rows={12} disabled={!editing.keywords} value={editor.activeKeywords} onChange={(event) => setEditor({ ...editor, activeKeywords: event.target.value })}/></label><label>کلیدواژه‌های حذف یا احتیاط<textarea rows={8} disabled={!editing.keywords} value={editor.excludedKeywords} onChange={(event) => setEditor({ ...editor, excludedKeywords: event.target.value })}/></label><label className={styles.fileBox}>بارگذاری فایل کلیدواژه<input type="file" disabled={!editing.keywords} accept=".txt,.md,.csv,.xlsx" onChange={(event) => loadText(event, "activeKeywords", "keywords")}/><small>{files.keywords.join("، ") || "فایلی انتخاب نشده است."}</small></label></div>{editing.keywords && <div className={styles.editorActions}><button className={styles.secondary} onClick={() => cancelSection("keywords")}>انصراف</button><button className={styles.primary} onClick={() => saveSection("keywords")}>ذخیره نسخه و قفل</button></div>}</article>}

      {managementView === "company" && <article className={styles.lockedCard}>{lockHeader("company", "پروفایل، صلاحیت‌ها و رزومه")}<div className={styles.fields}><label>پروفایل خلاصه شرکت<textarea rows={7} disabled={!editing.company} value={editor.profile} onChange={(event) => setEditor({ ...editor, profile: event.target.value })}/></label><label className={styles.fileBox}>بارگذاری فایل پروفایل<input type="file" disabled={!editing.company} accept=".txt,.md,.pdf,.docx" onChange={(event) => loadText(event, "profile", "profile")}/><small>{files.profile.join("، ") || "فایلی انتخاب نشده است."}</small></label><label>صلاحیت‌ها و رتبه‌ها<textarea rows={9} disabled={!editing.company} value={editor.qualifications} onChange={(event) => setEditor({ ...editor, qualifications: event.target.value })}/></label><label className={styles.fileBox}>بارگذاری فایل صلاحیت‌ها<input type="file" disabled={!editing.company} accept=".txt,.md,.pdf,.docx,.xlsx" onChange={(event) => loadText(event, "qualifications", "qualifications")}/><small>{files.qualifications.join("، ") || "فایلی انتخاب نشده است."}</small></label><label>خلاصه سوابق و تجربیات<textarea rows={10} disabled={!editing.company} value={editor.experience} onChange={(event) => setEditor({ ...editor, experience: event.target.value })}/></label><label className={styles.fileBox}>بارگذاری رزومه شرکت<input type="file" disabled={!editing.company} accept=".txt,.md,.pdf,.docx" onChange={(event) => loadText(event, "experience", "resume")}/><small>{files.resume.join("، ") || "فایلی انتخاب نشده است."}</small></label></div>{editing.company && <div className={styles.editorActions}><button className={styles.secondary} onClick={() => cancelSection("company")}>انصراف</button><button className={styles.primary} onClick={() => saveSection("company")}>ذخیره نسخه و قفل</button></div>}</article>}

      {managementView === "versions" && <div className={styles.managementGrid}><article className={styles.panel}><h2>نسخه‌های زمینه تحلیل</h2>{versions.map((item) => <div className={styles.versionItem} key={item.version}><span><b>نسخه {fa.format(item.version)}</b><small>{item.status}</small></span>{item.status === "پیش‌نویس" && <button className={styles.primary} onClick={() => { setVersions((items) => items.map((version) => ({ ...version, status: version.version === item.version ? "فعال" : version.status === "فعال" ? "بازنشسته" : version.status }))); notify("نسخه فعال شد؛ ChatGPT در اجرای بعدی تغییر را می‌خواند."); }}>فعال‌سازی</button>}</div>)}</article><article className={styles.panel}><h2>قاعده نسخه‌بندی</h2><ul><li>ویرایش‌ها ابتدا Snapshot پیش‌نویس می‌سازند.</li><li>نسخه فعال مستقیماً تغییر نمی‌کند.</li><li>فعال‌سازی نیازمند اقدام مدیر است.</li><li>Scheduled Task فقط هنگام تغییر نسخه Snapshot جدید را می‌خواند.</li></ul></article></div>}
    </section>}

    {selected && <div className={styles.backdrop} onMouseDown={() => setSelected(null)}><section className={styles.modal} onMouseDown={(event) => event.stopPropagation()}><header><div><small>{selected.status}</small><h2>{selected.title}</h2><p>{selected.employer}</p></div><button onClick={() => setSelected(null)}>×</button></header><div className={styles.modalBody}><dl><div><dt>وضعیت</dt><dd>{selected.status}</dd></div><div><dt>اقدام بعدی</dt><dd>{selected.next}</dd></div><div><dt>زمان</dt><dd>{urgency(selected.deadline).remaining}</dd></div></dl></div></section></div>}
  </main>;
}
