"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./procurement.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type Notice = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  submission_deadline: string | null;
  processing_status_label: string;
  is_recommended: boolean;
  case_stage_label?: string | null;
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

export default function ProcurementPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [tenders, setTenders] = useState<Notice[]>([]);
  const [inquiries, setInquiries] = useState<Notice[]>([]);
  const [opportunities, setOpportunities] = useState<DirectOpportunity[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [automation, setAutomation] = useState<AutomationSettings | null>(null);
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>([]);
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
        if (responses.some((response) => response.status === 401 || response.status === 403)) {
          throw new Error("برای مشاهده این بخش ابتدا وارد PDP One شوید.");
        }
        if (responses.some((response) => !response.ok)) throw new Error("دریافت اطلاعات زیرسامانه کامل نشد.");
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
        setAutomation(itemsOf<AutomationSettings>(automationData)[0] || null);
        setSelectedConnectors(
          sourceItems.flatMap((source) => source.connectors.filter((connector) => source.enabled && connector.enabled).map((connector) => connector.id)),
        );
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "خطای ناشناخته");
      }
    }
    load();
    return () => { cancelled = true; };
  }, [refresh]);

  const filteredTenders = useMemo(
    () => tenders.filter((item) => !search || `${item.title} ${item.employer_name} ${item.province}`.includes(search)),
    [search, tenders],
  );
  const filteredInquiries = useMemo(
    () => inquiries.filter((item) => !search || `${item.title} ${item.employer_name} ${item.province}`.includes(search)),
    [inquiries, search],
  );

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 4000);
  }

  async function toggleSource(source: Source) {
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/sources/${source.id}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      if (!response.ok) throw new Error("تغییر وضعیت منبع فقط برای مدیر سامانه مجاز است.");
      notify(source.enabled ? "منبع از استخراج‌های بعدی خارج شد." : "منبع برای استخراج‌های بعدی فعال شد.");
      setRefresh((value) => value + 1);
    } catch (error) {
      notify(error instanceof Error ? error.message : "تغییر وضعیت انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  async function startExtraction() {
    if (!selectedConnectors.length) return notify("حداقل یک Connector فعال را انتخاب کنید.");
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/extraction-runs/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ connector_ids: selectedConnectors, include_details: true, analyze_after_success: false }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.connector_ids?.[0] || "استخراج شروع نشد.");
      notify(`استخراج در صف قرار گرفت. شناسه اجرا: ${String(payload.id).slice(0, 8)}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "استخراج شروع نشد.");
    } finally {
      setBusy(false);
    }
  }

  async function createDirectOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/direct-opportunities/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({
          title: form.get("title"),
          employer_name: form.get("employer_name"),
          next_action: form.get("next_action"),
        }),
      });
      if (!response.ok) throw new Error("ثبت فرصت انجام نشد.");
      event.currentTarget.reset();
      notify("فرصت خارج از سامانه ثبت شد.");
      setRefresh((value) => value + 1);
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت فرصت انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  const displayedNotices = tab === "tenders" ? filteredTenders : filteredInquiries;

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}>
      <div><span>زیرسامانه تخصصی PDP One</span><h1>فرصت‌ها و مناقصات</h1><p>استخراج، تحلیل ChatGPT، پیگیری و تصمیم‌سازی در یک مسیر کنترل‌شده</p></div>
      <div className={styles.headerActions}><a href="/">بازگشت به سامانه</a><button disabled={busy} onClick={startExtraction}>استخراج اکنون</button></div>
    </header>

    <nav className={styles.tabs}>
      {([
        ["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"],
        ["direct", "فرصت‌های خارج از سامانه"], ["management", "مدیریت زیرسامانه"],
      ] as [Tab, string][]).map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => setTab(id)}>{label}</button>)}
    </nav>

    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article><span>کل فراخوان‌ها</span><b>{faNumber.format(dashboard?.notices.total || 0)}</b><small>مناقصه و استعلام</small></article>
        <article><span>پیشنهادی ChatGPT</span><b>{faNumber.format(dashboard?.notices.recommended || 0)}</b><small>نیازمند تصمیم انسانی</small></article>
        <article><span>پرونده فعال</span><b>{faNumber.format(dashboard?.cases.active || 0)}</b><small>{faNumber.format(dashboard?.cases.overdue_next_actions || 0)} اقدام عقب‌افتاده</small></article>
        <article><span>Connector فعال</span><b>{faNumber.format(dashboard?.sources.enabled_connectors || 0)}</b><small>{faNumber.format(dashboard?.sources.pending_connectors || 0)} مورد در انتظار بررسی</small></article>
      </div>
      <div className={styles.grid}>
        <article className={styles.panel}><h2>وضعیت تحلیل ChatGPT</h2><p>اجرای دستی در گفت‌وگوی اختصاصی Scheduled Task فقط با کلمه زیر انجام می‌شود:</p><strong className={styles.command}>{automation?.manual_command || "PDP"}</strong><small>نتیجه‌ها فقط به‌صورت پیش‌نویس در پیشنهادات ثبت می‌شوند.</small></article>
        <article className={styles.panel}><h2>برنامه فعلی</h2><dl><div><dt>استخراج خودکار</dt><dd>{automation?.enabled ? "فعال" : "غیرفعال تا تأیید Preview"}</dd></div><div><dt>دوره</dt><dd>{automation?.cadence_label || "تعیین نشده"}</dd></div><div><dt>تأخیر تحلیل</dt><dd>{faNumber.format(automation?.analysis_delay_minutes || 60)} دقیقه</dd></div><div><dt>اجرای بعدی</dt><dd>{displayDate(automation?.next_extraction_at || null)}</dd></div></dl></article>
      </div>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما یا استان..." /><span>{faNumber.format(displayedNotices.length)} رکورد</span></div>
      <div className={styles.list}>{displayedNotices.map((item) => <article key={item.id}>
        <div><small>{item.province || "استان نامشخص"} · {item.processing_status_label}</small><h3>{item.title}</h3><p>{item.employer_name || "کارفرما ثبت نشده"}</p></div>
        <div className={styles.noticeMeta}><span>{item.is_recommended ? "پیشنهادی" : "در انتظار تحلیل"}</span><small>مهلت: {displayDate(item.submission_deadline)}</small><button>مشاهده</button></div>
      </article>)}</div>
    </section>}

    {tab === "direct" && <section className={styles.grid}>
      <article className={styles.panel}><h2>ثبت سریع فرصت</h2><form className={styles.form} onSubmit={createDirectOpportunity}><label>عنوان فرصت<input name="title" required /></label><label>کارفرما<input name="employer_name" required /></label><label>اقدام بعدی<input name="next_action" required /></label><button disabled={busy}>ثبت فرصت</button></form></article>
      <article className={styles.panel}><h2>فرصت‌های در جریان</h2><div className={styles.compactList}>{opportunities.map((item) => <div key={item.id}><b>{item.title}</b><span>{item.employer_name}</span><small>{item.stage_label} · {item.next_action}</small></div>)}</div></article>
    </section>}

    {tab === "management" && <section className={styles.grid}>
      <article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.sourceList}>{sources.map((source) => <div key={source.id}><label><input type="checkbox" checked={source.enabled} disabled={busy} onChange={() => toggleSource(source)} /><b>{source.name}</b></label><span>{source.status_label}</span><small>{source.connectors.map((connector) => `${connector.notice_type_label}: ${connector.enabled ? "فعال" : "غیرفعال"}`).join(" · ")}</small></div>)}</div></article>
      <article className={styles.panel}><h2>Connectorهای اجرای دستی</h2><div className={styles.connectorList}>{sources.flatMap((source) => source.connectors).map((connector) => <label key={connector.id}><input type="checkbox" checked={selectedConnectors.includes(connector.id)} disabled={!connector.enabled || busy} onChange={(event) => setSelectedConnectors((items) => event.target.checked ? [...items, connector.id] : items.filter((id) => id !== connector.id))} /><span>{connector.key}</span><small>{connector.status_label}</small></label>)}</div><button className={styles.fullButton} disabled={busy} onClick={startExtraction}>شروع استخراج منابع انتخاب‌شده</button></article>
    </section>}
  </main>;
}
