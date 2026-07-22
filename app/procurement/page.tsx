"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./procurement.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type NoticeView = "all" | "recommended" | "selected" | "preparation" | "submitted" | "results";
type DataMode = "loading" | "live" | "demo";

type Notice = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  submission_deadline: string | null;
  processing_status_label: string;
  is_recommended: boolean;
  case_stage_label?: string | null;
  result_label?: string | null;
};

type Connector = {
  id: string;
  key: string;
  notice_type_label: string;
  enabled: boolean;
  status_label: string;
};

type Source = {
  id: string;
  name: string;
  enabled: boolean;
  status_label: string;
  connectors: Connector[];
};

type DirectOpportunity = {
  id: string;
  title: string;
  employer_name: string;
  stage_label: string;
  next_action: string;
  next_action_due: string | null;
};

type AutomationSettings = {
  id: string;
  enabled: boolean;
  cadence_label: string;
  interval_minutes: number;
  daily_time: string | null;
  analysis_delay_minutes: number;
  next_extraction_at: string | null;
  manual_command: string;
};

type Dashboard = {
  notices: { total: number; tenders: number; inquiries: number; recommended: number; deadline_passed: number };
  cases: { active: number; overdue_next_actions: number; without_responsible: number };
  sources: { enabled_sites: number; enabled_connectors: number; pending_connectors: number };
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const faNumber = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "short", day: "numeric" });

const seedDashboard: Dashboard = {
  notices: { total: 186, tenders: 118, inquiries: 68, recommended: 17, deadline_passed: 9 },
  cases: { active: 12, overdue_next_actions: 3, without_responsible: 2 },
  sources: { enabled_sites: 2, enabled_connectors: 4, pending_connectors: 2 },
};

const seedTenders: Notice[] = [
  { id: "T-001", title: "خدمات مشاوره طراحی و نظارت مجموعه اداری", employer_name: "شرکت توسعه عمران", province: "تهران", submission_deadline: "2026-08-12", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب" },
  { id: "T-002", title: "مطالعات طرح جامع و برنامه‌ریزی فضایی", employer_name: "اداره کل راه و شهرسازی", province: "فارس", submission_deadline: "2026-08-09", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "در دست تهیه" },
  { id: "T-003", title: "طراحی تأسیسات مکانیکی و برقی بیمارستان", employer_name: "دانشگاه علوم پزشکی", province: "البرز", submission_deadline: "2026-08-16", processing_status_label: "در انتظار تحلیل", is_recommended: false, case_stage_label: null },
  { id: "T-004", title: "مطالعات امکان‌سنجی شهرک صنعتی", employer_name: "شرکت شهرک‌های صنعتی", province: "آذربایجان شرقی", submission_deadline: "2026-08-05", processing_status_label: "ارسال‌شده", is_recommended: true, case_stage_label: "ارسال‌شده" },
  { id: "T-005", title: "خدمات طراحی معماری مجتمع آموزشی", employer_name: "سازمان نوسازی مدارس", province: "قم", submission_deadline: "2026-07-30", processing_status_label: "نتیجه ثبت‌شده", is_recommended: true, case_stage_label: "نتایج", result_label: "برنده" },
];

const seedInquiries: Notice[] = [
  { id: "I-001", title: "استعلام خدمات نقشه‌برداری و برداشت وضع موجود", employer_name: "شهرداری منطقه", province: "تهران", submission_deadline: "2026-07-25", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب" },
  { id: "I-002", title: "استعلام تهیه گزارش توجیهی و امکان‌سنجی", employer_name: "منطقه ویژه اقتصادی", province: "بوشهر", submission_deadline: "2026-07-26", processing_status_label: "در دست تهیه", is_recommended: true, case_stage_label: "در دست تهیه" },
  { id: "I-003", title: "استعلام طراحی روشنایی محوطه صنعتی", employer_name: "شرکت تولیدی نمونه", province: "قزوین", submission_deadline: "2026-07-24", processing_status_label: "در انتظار تحلیل", is_recommended: false, case_stage_label: null },
  { id: "I-004", title: "استعلام بازنگری نقشه‌های معماری", employer_name: "شرکت عمران و مسکن", province: "مازندران", submission_deadline: "2026-07-23", processing_status_label: "نتیجه ثبت‌شده", is_recommended: true, case_stage_label: "نتایج", result_label: "ناموفق" },
];

const seedOpportunities: DirectOpportunity[] = [
  { id: "D-001", title: "رایزنی طرح توسعه پردیس اداری", employer_name: "گروه سرمایه‌گذاری پارس", stage_label: "در حال مذاکره", next_action: "ارسال معرفی‌نامه سوابق", next_action_due: "2026-07-24" },
  { id: "D-002", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer_name: "شرکت انرژی نو", stage_label: "در حال پیگیری", next_action: "هماهنگی جلسه فنی", next_action_due: "2026-07-25" },
  { id: "D-003", title: "دعوت محدود طراحی مجموعه درمانی", employer_name: "بنیاد توسعه سلامت", stage_label: "در دست تهیه پیشنهاد", next_action: "تکمیل تیم پیشنهادی", next_action_due: "2026-07-27" },
];

const seedSources: Source[] = [
  { id: "S-H", name: "هزاره", enabled: true, status_label: "فعال", connectors: [
    { id: "C-HT", key: "hezareh_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده اجرا" },
    { id: "C-HI", key: "hezareh_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده اجرا" },
  ] },
  { id: "S-P", name: "پارس نماد داده", enabled: true, status_label: "فعال", connectors: [
    { id: "C-PT", key: "parsnamad_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده اجرا" },
    { id: "C-PI", key: "parsnamad_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده اجرا" },
  ] },
  { id: "S-S", name: "ستاد ایران", enabled: false, status_label: "موقتاً تعلیق‌شده / نیازمند بررسی مجدد در ساعت دسترسی", connectors: [
    { id: "C-ST", key: "setad_tenders", notice_type_label: "مناقصات", enabled: false, status_label: "نیازمند بررسی" },
    { id: "C-SI", key: "setad_inquiries", notice_type_label: "استعلامات", enabled: false, status_label: "نیازمند بررسی" },
  ] },
];

const seedAutomation: AutomationSettings = {
  id: "A-001", enabled: false, cadence_label: "روزانه", interval_minutes: 60, daily_time: "17:00",
  analysis_delay_minutes: 60, next_extraction_at: null, manual_command: "PDP",
};

function itemsOf<T>(payload: T[] | { results?: T[] }): T[] {
  return Array.isArray(payload) ? payload : payload.results || [];
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include" });
  if (!response.ok) throw new Error("دریافت نشست کاربر انجام نشد.");
  return String((await response.json()).csrf_token);
}

function displayDate(value: string | null) {
  return value ? faDate.format(new Date(value)) : "تعیین نشده";
}

function matchesView(item: Notice, view: NoticeView) {
  if (view === "all") return true;
  if (view === "recommended") return item.is_recommended;
  if (view === "selected") return item.case_stage_label === "منتخب";
  if (view === "preparation") return item.case_stage_label === "در دست تهیه";
  if (view === "submitted") return item.case_stage_label === "ارسال‌شده";
  return item.case_stage_label === "نتایج" || Boolean(item.result_label);
}

export default function ProcurementPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<NoticeView>("all");
  const [mode, setMode] = useState<DataMode>("loading");
  const [dashboard, setDashboard] = useState<Dashboard>(seedDashboard);
  const [tenders, setTenders] = useState<Notice[]>(seedTenders);
  const [inquiries, setInquiries] = useState<Notice[]>(seedInquiries);
  const [opportunities, setOpportunities] = useState<DirectOpportunity[]>(seedOpportunities);
  const [sources, setSources] = useState<Source[]>(seedSources);
  const [automation, setAutomation] = useState<AutomationSettings>(seedAutomation);
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>(["C-HT", "C-HI", "C-PT", "C-PI"]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const responses = await Promise.all([
          fetch(`${API_BASE}/procurement/dashboard/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/tenders/?ordering=-last_seen_at`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/inquiries/?ordering=-last_seen_at`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/direct-opportunities/?ordering=next_action_due`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/sources/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/automation-settings/`, { credentials: "include" }),
        ]);
        if (responses.some((response) => !response.ok)) throw new Error("preview-backend-unavailable");
        const [dashboardData, tenderData, inquiryData, directData, sourceData, automationData] = await Promise.all(
          responses.map((response) => response.json()),
        );
        if (cancelled) return;
        const sourceItems = itemsOf<Source>(sourceData);
        setDashboard(dashboardData as Dashboard);
        setTenders(itemsOf<Notice>(tenderData));
        setInquiries(itemsOf<Notice>(inquiryData));
        setOpportunities(itemsOf<DirectOpportunity>(directData));
        setSources(sourceItems);
        setAutomation(itemsOf<AutomationSettings>(automationData)[0] || seedAutomation);
        setSelectedConnectors(sourceItems.flatMap((source) => source.connectors.filter((connector) => source.enabled && connector.enabled).map((connector) => connector.id)));
        setMode("live");
      } catch {
        if (!cancelled) {
          setMode("demo");
          setDashboard(seedDashboard);
          setTenders(seedTenders);
          setInquiries(seedInquiries);
          setOpportunities(seedOpportunities);
          setSources(seedSources);
          setAutomation(seedAutomation);
          setSelectedConnectors(["C-HT", "C-HI", "C-PT", "C-PI"]);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [refresh]);

  const displayedNotices = useMemo(() => {
    const base = tab === "tenders" ? tenders : inquiries;
    return base.filter((item) => matchesView(item, noticeView) && (!search || `${item.title} ${item.employer_name} ${item.province}`.includes(search)));
  }, [inquiries, noticeView, search, tab, tenders]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 4000);
  }

  async function toggleSource(source: Source) {
    if (mode === "demo") {
      setSources((items) => items.map((item) => item.id === source.id ? {
        ...item,
        enabled: !item.enabled,
        status_label: item.enabled ? "غیرفعال توسط کاربر" : "فعال",
        connectors: item.connectors.map((connector) => ({ ...connector, enabled: item.enabled ? false : connector.key.startsWith("setad_") ? false : true })),
      } : item));
      notify(source.enabled ? "منبع در Preview از استخراج خارج شد؛ داده قبلی حذف نمی‌شود." : "منبع در Preview فعال شد.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/sources/${source.id}/`, {
        method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      if (!response.ok) throw new Error("تغییر وضعیت منبع فقط برای مدیر سامانه مجاز است.");
      notify(source.enabled ? "منبع از استخراج‌های بعدی خارج شد." : "منبع برای استخراج‌های بعدی فعال شد.");
      setRefresh((value) => value + 1);
    } catch (error) {
      notify(error instanceof Error ? error.message : "تغییر وضعیت انجام نشد.");
    } finally { setBusy(false); }
  }

  async function startExtraction() {
    if (!selectedConnectors.length) return notify("حداقل یک Connector فعال را انتخاب کنید.");
    if (mode === "demo") {
      setBusy(true);
      notify("اجرای نمونه آغاز شد؛ در Preview هیچ اتصال شبکه یا ثبت واقعی انجام نمی‌شود.");
      window.setTimeout(() => { setBusy(false); notify("استخراج نمایشی با موفقیت پایان یافت: ۲۴ رکورد جدید و ۳ رکورد به‌روزرسانی‌شده."); }, 900);
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/extraction-runs/`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ connector_ids: selectedConnectors, include_details: true, analyze_after_success: false }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.connector_ids?.[0] || "استخراج شروع نشد.");
      notify(`استخراج در صف قرار گرفت. شناسه اجرا: ${String(payload.id).slice(0, 8)}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "استخراج شروع نشد.");
    } finally { setBusy(false); }
  }

  async function createDirectOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (mode === "demo") {
      setOpportunities((items) => [{
        id: `D-${Date.now()}`,
        title: String(form.get("title")),
        employer_name: String(form.get("employer_name")),
        stage_label: "فرصت جدید",
        next_action: String(form.get("next_action")),
        next_action_due: new Date(Date.now() + 86400000).toISOString(),
      }, ...items]);
      event.currentTarget.reset();
      notify("فرصت به‌صورت نمونه در Preview ثبت شد.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/direct-opportunities/`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ title: form.get("title"), employer_name: form.get("employer_name"), next_action: form.get("next_action") }),
      });
      if (!response.ok) throw new Error("ثبت فرصت انجام نشد.");
      event.currentTarget.reset();
      notify("فرصت خارج از سامانه ثبت شد.");
      setRefresh((value) => value + 1);
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت فرصت انجام نشد.");
    } finally { setBusy(false); }
  }

  const tabs: [Tab, string][] = [
    ["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"],
    ["direct", "فرصت‌های خارج از سامانه"], ["management", "مدیریت زیرسامانه"],
  ];
  const views: [NoticeView, string][] = [
    ["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"],
    ["preparation", "در دست تهیه"], ["submitted", "ارسال‌شده"], ["results", "نتایج"],
  ];

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}>
      <div><span>زیرسامانه تخصصی PDP One</span><h1>فرصت‌ها و مناقصات</h1><p>استخراج، تحلیل ChatGPT، پیگیری و تصمیم‌سازی در یک مسیر کنترل‌شده</p></div>
      <div className={styles.headerActions}><a href="/">بازگشت به سامانه</a><button disabled={busy} onClick={startExtraction}>{busy ? "در حال اجرا..." : "استخراج اکنون"}</button></div>
    </header>

    {mode !== "live" && <div className={styles.demoBanner}><b>{mode === "loading" ? "در حال بررسی اتصال..." : "حالت Preview تعاملی"}</b><span>{mode === "demo" ? "داده‌ها نمونه‌اند و هیچ تغییری در سامانه واقعی ایجاد نمی‌شود." : "در صورت نبود Backend، داده نمونه بارگذاری می‌شود."}</span></div>}

    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setNoticeView("all"); }}>{label}</button>)}</nav>

    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article><span>کل فراخوان‌ها</span><b>{faNumber.format(dashboard.notices.total)}</b><small>{faNumber.format(dashboard.notices.tenders)} مناقصه و {faNumber.format(dashboard.notices.inquiries)} استعلام</small></article>
        <article><span>پیشنهادی ChatGPT</span><b>{faNumber.format(dashboard.notices.recommended)}</b><small>نیازمند تصمیم انسانی</small></article>
        <article><span>پرونده فعال</span><b>{faNumber.format(dashboard.cases.active)}</b><small>{faNumber.format(dashboard.cases.overdue_next_actions)} اقدام عقب‌افتاده</small></article>
        <article><span>Connector فعال</span><b>{faNumber.format(dashboard.sources.enabled_connectors)}</b><small>{faNumber.format(dashboard.sources.pending_connectors)} مورد نیازمند بررسی</small></article>
      </div>
      <div className={styles.grid}>
        <article className={styles.panel}><h2>وضعیت تحلیل ChatGPT</h2><p>اجرای دستی در گفت‌وگوی اختصاصی Scheduled Task فقط با کلمه زیر انجام می‌شود:</p><strong className={styles.command}>{automation.manual_command}</strong><small>نتیجه‌ها فقط به‌صورت پیش‌نویس در پیشنهادات ثبت می‌شوند.</small></article>
        <article className={styles.panel}><h2>برنامه فعلی</h2><dl><div><dt>استخراج خودکار</dt><dd>{automation.enabled ? "فعال" : "غیرفعال تا تأیید Preview"}</dd></div><div><dt>دوره</dt><dd>{automation.cadence_label} {automation.daily_time ? `ساعت ${automation.daily_time}` : ""}</dd></div><div><dt>تأخیر تحلیل</dt><dd>{faNumber.format(automation.analysis_delay_minutes)} دقیقه</dd></div><div><dt>اجرای بعدی</dt><dd>{displayDate(automation.next_extraction_at)}</dd></div></dl></article>
        <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>۳ اقدام پیگیری عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>۴ فراخوان نزدیک به مهلت</span></div></article>
        <article className={styles.panel}><h2>قیف فرصت‌ها</h2><div className={styles.funnel}><span>استخراج‌شده ۱۸۶</span><span>پیشنهادی ۱۷</span><span>منتخب ۹</span><span>در دست تهیه ۵</span><span>ارسال‌شده ۳</span></div></article>
      </div>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <div className={styles.sectionHeading}><div><span>{tab === "tenders" ? "فرآیند مناقصات" : "فرآیند استعلامات"}</span><h2>{tab === "tenders" ? "مناقصات" : "استعلامات"}</h2></div><small>تمام نماها از همان رکورد واحد استفاده می‌کنند و داده تکراری ساخته نمی‌شود.</small></div>
      <div className={styles.viewTabs}>{views.map(([id, label]) => <button key={id} className={noticeView === id ? styles.selectedView : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div>
      <div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما یا استان..." /><span>{faNumber.format(displayedNotices.length)} رکورد</span></div>
      <div className={styles.list}>{displayedNotices.map((item) => <article key={item.id}>
        <div><small>{item.province || "استان نامشخص"} · {item.processing_status_label}</small><h3>{item.title}</h3><p>{item.employer_name || "کارفرما ثبت نشده"}</p></div>
        <div className={styles.noticeMeta}><span>{item.result_label || item.case_stage_label || (item.is_recommended ? "پیشنهادی" : "در انتظار تحلیل")}</span><small>مهلت: {displayDate(item.submission_deadline)}</small><div><button onClick={() => notify("صفحه جزئیات چهار‌بخشی در Preview عملیاتی نمایش داده خواهد شد.")}>مشاهده</button><button onClick={() => notify("عملیات انتخاب در Preview فقط نمایشی است.")}>انتخاب</button></div></div>
      </article>)}{!displayedNotices.length && <div className={styles.empty}>رکوردی مطابق این نما و جست‌وجو وجود ندارد.</div>}</div>
    </section>}

    {tab === "direct" && <section>
      <div className={styles.sectionHeading}><div><span>ثبت و پیگیری سریع</span><h2>فرصت‌های خارج از سامانه</h2></div><small>ثبت اولیه با سه فیلد و در کمتر از یک دقیقه انجام می‌شود.</small></div>
      <div className={styles.grid}>
        <article className={styles.panel}><h2>ثبت سریع فرصت</h2><form className={styles.form} onSubmit={createDirectOpportunity}><label>عنوان فرصت<input name="title" required /></label><label>کارفرما<input name="employer_name" required /></label><label>اقدام بعدی<input name="next_action" required /></label><button disabled={busy}>ثبت فرصت</button></form></article>
        <article className={styles.panel}><h2>فرصت‌های در جریان</h2><div className={styles.compactList}>{opportunities.map((item) => <div key={item.id}><b>{item.title}</b><span>{item.employer_name}</span><small>{item.stage_label} · {item.next_action} · {displayDate(item.next_action_due)}</small></div>)}</div></article>
      </div>
    </section>}

    {tab === "management" && <section>
      <div className={styles.sectionHeading}><div><span>کنترل منابع و زمان‌بندی</span><h2>مدیریت زیرسامانه</h2></div><small>در استخراج فقط سایت‌ها و Connectorهای دارای تیک اجرا می‌شوند.</small></div>
      <div className={styles.grid}>
        <article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.sourceList}>{sources.map((source) => <div key={source.id}><label><input type="checkbox" checked={source.enabled} disabled={busy} onChange={() => toggleSource(source)} /><b>{source.name}</b></label><span>{source.status_label}</span><small>{source.connectors.map((connector) => `${connector.notice_type_label}: ${connector.enabled ? "فعال" : "غیرفعال"}`).join(" · ")}</small></div>)}</div></article>
        <article className={styles.panel}><h2>Connectorهای اجرای دستی</h2><div className={styles.connectorList}>{sources.flatMap((source) => source.connectors).map((connector) => <label key={connector.id}><input type="checkbox" checked={selectedConnectors.includes(connector.id)} disabled={!connector.enabled || busy} onChange={(event) => setSelectedConnectors((items) => event.target.checked ? [...new Set([...items, connector.id])] : items.filter((id) => id !== connector.id))} /><span>{connector.key}</span><small>{connector.status_label}</small></label>)}</div><button className={styles.fullButton} disabled={busy} onClick={startExtraction}>شروع استخراج منابع انتخاب‌شده</button></article>
        <article className={styles.panel}><h2>زمان‌بندی استخراج</h2><dl><div><dt>نوع برنامه</dt><dd>{automation.cadence_label}</dd></div><div><dt>ساعت روزانه</dt><dd>{automation.daily_time || "تعیین نشده"}</dd></div><div><dt>تأخیر تحلیل ChatGPT</dt><dd>{automation.analysis_delay_minutes} دقیقه</dd></div><div><dt>فرمان دستی</dt><dd>{automation.manual_command}</dd></div></dl></article>
        <article className={styles.panel}><h2>تنظیمات تحلیل هوشمند</h2><dl><div><dt>موتور تحلیل</dt><dd>ChatGPT + MCP</dd></div><div><dt>OpenAI API پولی</dt><dd>استفاده نمی‌شود</dd></div><div><dt>زمینه تحلیل</dt><dd>Snapshot نسخه‌بندی‌شده</dd></div><div><dt>ثبت خروجی</dt><dd>Draft-first</dd></div></dl></article>
      </div>
    </section>}
  </main>;
}
