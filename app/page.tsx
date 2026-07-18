"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Page = "dashboard" | "contracts" | "finance" | "projects" | "tenders" | "analysis";
type Status = "فعال" | "در انتظار" | "بحرانی" | "پیش‌نویس";
type Contract = { id: string; title: string; employer: string; field: string; value: string; progress: number; status: Status; due: string };
type FinanceStatus = "پیش‌نویس" | "باز" | "معوق" | "سررسید نزدیک" | "در انتظار تأیید" | "وصول شده" | "لغوشده";
type FinanceFilter = "همه" | FinanceStatus;
type Receivable = { recordId?: string; id: string; contractId: string; title: string; employer: string; statement: string; amount: string; received: string; due: string; status: FinanceStatus };
type FinanceMode = "loading" | "live" | "auth" | "demo";
type ApiReceivable = { id: string; reference_code: string; contract_code: string; contract_title: string; employer: string; statement_title: string; amount_rials: string; received_rials: string; due_date: string; status_label: FinanceStatus };
type FinanceSummary = { openAmount: string; overdueAmount: string; collectedAmount: string; dueSoonCount: number; openCount: number };

const seedContracts: Contract[] = [
  { id: "TEST-1405-001", title: "قرارداد آزمایشی مطالعات و طراحی دفتر مرکزی", employer: "شرکت نمونه آزمایشی", field: "معماری", value: "۱.۲۵ میلیارد", progress: 0, status: "پیش‌نویس", due: "۳۰ آذر ۱۴۰۵" },
  { id: "PDP-1405-012", title: "مطالعات طرح جامع شهرک صنعتی صفادشت", employer: "شرکت شهرک‌های صنعتی تهران", field: "برنامه‌ریزی فضایی", value: "۱۲.۸ میلیارد", progress: 72, status: "فعال", due: "۲۸ مرداد ۱۴۰۵" },
  { id: "PDP-1405-009", title: "طراحی معماری مجموعه اداری مرکزی", employer: "سازمان منطقه آزاد", field: "معماری", value: "۸.۴ میلیارد", progress: 48, status: "در انتظار", due: "۱۲ شهریور ۱۴۰۵" },
  { id: "PDP-1404-031", title: "خدمات مشاور تاسیسات مکانیکی بیمارستان", employer: "دانشگاه علوم پزشکی", field: "تاسیسات", value: "۵.۹ میلیارد", progress: 89, status: "بحرانی", due: "۵ مرداد ۱۴۰۵" },
  { id: "PDP-1405-015", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی آفتاب", field: "انرژی", value: "۳.۶ میلیارد", progress: 16, status: "فعال", due: "۲۲ آبان ۱۴۰۵" },
];

const seedReceivables: Receivable[] = [
  { id: "FIN-1405-041", contractId: "PDP-1405-012", title: "مطالعات طرح جامع شهرک صنعتی صفادشت", employer: "شرکت شهرک‌های صنعتی تهران", statement: "صورت‌وضعیت شماره ۶", amount: "۵.۴ میلیارد", received: "۱.۲ میلیارد", due: "۲ تیر ۱۴۰۵", status: "معوق" },
  { id: "FIN-1405-044", contractId: "PDP-1405-009", title: "طراحی معماری مجموعه اداری مرکزی", employer: "سازمان منطقه آزاد", statement: "صورت‌وضعیت شماره ۳", amount: "۳.۸ میلیارد", received: "—", due: "۳۱ تیر ۱۴۰۵", status: "سررسید نزدیک" },
  { id: "FIN-1405-039", contractId: "PDP-1404-031", title: "خدمات مشاور تاسیسات مکانیکی بیمارستان", employer: "دانشگاه علوم پزشکی", statement: "صورت‌وضعیت شماره ۹", amount: "۴.۳ میلیارد", received: "—", due: "۱۸ خرداد ۱۴۰۵", status: "معوق" },
  { id: "FIN-1405-046", contractId: "PDP-1405-015", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی آفتاب", statement: "پیش‌پرداخت مرحله اول", amount: "۱.۱ میلیارد", received: "—", due: "۸ مرداد ۱۴۰۵", status: "در انتظار تأیید" },
  { id: "FIN-1405-035", contractId: "PDP-1405-012", title: "مطالعات طرح جامع شهرک صنعتی صفادشت", employer: "شرکت شهرک‌های صنعتی تهران", statement: "صورت‌وضعیت شماره ۵", amount: "۶.۲ میلیارد", received: "۶.۲ میلیارد", due: "۱۵ اردیبهشت ۱۴۰۵", status: "وصول شده" },
];

const demoFinanceSummary: FinanceSummary = { openAmount: "۲۶.۴", overdueAmount: "۹.۷", collectedAmount: "۴۸.۲", dueSoonCount: 3, openCount: 7 };

const nav: { id: Page; label: string; icon: string }[] = [
  { id: "dashboard", label: "داشبورد مدیریت", icon: "◫" },
  { id: "contracts", label: "قراردادها", icon: "▤" },
  { id: "finance", label: "مالی و مطالبات", icon: "◈" },
  { id: "projects", label: "پروژه‌ها", icon: "◇" },
  { id: "tenders", label: "مناقصات و فرصت‌ها", icon: "◎" },
  { id: "analysis", label: "تحلیل‌های هوشمند", icon: "✦" },
];

const stats = [
  ["قرارداد فعال", "۱۸", "+۲ این ماه", "blue"],
  ["مطالبات باز", "۲۶.۴", "میلیارد تومان", "amber"],
  ["فرصت مناسب", "۱۲", "از ۴۷ آگهی جدید", "teal"],
  ["پروژه پرریسک", "۳", "نیازمند تصمیم", "red"],
];

const statusClass = (status: Status) => `status ${status === "فعال" ? "ok" : status === "بحرانی" ? "danger" : status === "پیش‌نویس" ? "draft" : "waiting"}`;
const financeStatusClass = (status: FinanceStatus) => `finance-status ${status === "وصول شده" ? "paid" : status === "معوق" ? "overdue" : status === "سررسید نزدیک" ? "soon" : status === "پیش‌نویس" || status === "لغوشده" ? "draft" : "review"}`;
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const numberFa = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const dateFa = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric" });

function displayRials(value: string) {
  const amount = Number(value);
  return amount ? `${numberFa.format(amount / 10_000_000_000)} میلیارد` : "—";
}

function billionValue(value: string | number) {
  return numberFa.format(Number(value) / 10_000_000_000);
}

function mapApiReceivable(item: ApiReceivable): Receivable {
  return {
    recordId: item.id,
    id: item.reference_code,
    contractId: item.contract_code,
    title: item.contract_title,
    employer: item.employer,
    statement: item.statement_title,
    amount: displayRials(item.amount_rials),
    received: displayRials(item.received_rials),
    due: dateFa.format(new Date(`${item.due_date}T12:00:00`)),
    status: item.status_label,
  };
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("session-unavailable");
  return String((await response.json()).csrf_token);
}

export default function Home() {
  const [page, setPage] = useState<Page>("dashboard");
  const [menu, setMenu] = useState(false);
  const [modal, setModal] = useState(false);
  const [search, setSearch] = useState("");
  const [contracts, setContracts] = useState(seedContracts);
  const [financeFilter, setFinanceFilter] = useState<FinanceFilter>("همه");
  const [financeRecords, setFinanceRecords] = useState(seedReceivables);
  const [financeSummary, setFinanceSummary] = useState(demoFinanceSummary);
  const [financeMode, setFinanceMode] = useState<FinanceMode>("loading");
  const [financeModal, setFinanceModal] = useState(false);
  const [receiptModal, setReceiptModal] = useState(false);
  const [selectedReceivable, setSelectedReceivable] = useState<Receivable | null>(null);
  const [loginModal, setLoginModal] = useState(false);
  const [financeRefresh, setFinanceRefresh] = useState(0);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const results = useMemo(() => contracts.filter((c) => !search || [c.id, c.title, c.employer, c.field].some((v) => v.includes(search))), [contracts, search]);
  const receivables = useMemo(() => financeRecords.filter((item) => {
    const matchesFilter = financeFilter === "همه" || item.status === financeFilter;
    const matchesSearch = !search || [item.id, item.contractId, item.title, item.employer, item.statement].some((value) => value.includes(search));
    return matchesFilter && matchesSearch;
  }), [financeFilter, financeRecords, search]);

  useEffect(() => {
    if (page !== "finance") return;
    let cancelled = false;
    async function loadFinance() {
      setFinanceMode("loading");
      try {
        const response = await fetch(`${API_BASE}/receivables/?ordering=due_date`, { credentials: "include", headers: { Accept: "application/json" } });
        if (response.status === 401 || response.status === 403) {
          if (!cancelled) setFinanceMode("auth");
          return;
        }
        if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) throw new Error("api-unavailable");
        const payload = await response.json();
        const summaryResponse = await fetch(`${API_BASE}/financial-summary/`, { credentials: "include", headers: { Accept: "application/json" } });
        if (!summaryResponse.ok || !(summaryResponse.headers.get("content-type") || "").includes("application/json")) throw new Error("summary-unavailable");
        const summary = await summaryResponse.json();
        const items: ApiReceivable[] = Array.isArray(payload) ? payload : payload.results || [];
        if (!cancelled) {
          setFinanceRecords(items.map(mapApiReceivable));
          setFinanceSummary({ openAmount: billionValue(summary.open_amount_rials), overdueAmount: billionValue(summary.overdue_amount_rials), collectedAmount: billionValue(summary.collected_amount_rials), dueSoonCount: Number(summary.due_soon_count), openCount: Number(summary.open_count) });
          setFinanceMode("live");
        }
      } catch {
        if (!cancelled) {
          setFinanceRecords(seedReceivables);
          setFinanceSummary(demoFinanceSummary);
          setFinanceMode("demo");
        }
      }
    }
    loadFinance();
    return () => { cancelled = true; };
  }, [page, financeRefresh]);

  function navigate(next: Page) { setPage(next); setMenu(false); }
  function notify(message: string) { setToast(message); window.setTimeout(() => setToast(""), 2600); }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setContracts((items) => [{
      id: `PDP-1405-${String(items.length + 16).padStart(3, "0")}`,
      title: String(form.get("title")), employer: String(form.get("employer")), field: String(form.get("field")),
      value: `${String(form.get("value") || "—")} میلیارد`, progress: 0, status: "پیش‌نویس", due: "تعیین نشده",
    }, ...items]);
    setModal(false); setPage("contracts"); notify("پیش‌نویس قرارداد ثبت شد");
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/auth/login/`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "ورود انجام نشد.");
      setLoginModal(false); setFinanceRefresh((value) => value + 1); notify(`ورود ${payload.username} موفق بود`);
    } catch (error) {
      notify(error instanceof Error && error.message !== "session-unavailable" ? error.message : "ارتباط با سرور ورود برقرار نشد");
    } finally { setSaving(false); }
  }

  async function submitReceivable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/receivables/`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({
          contract_code: form.get("contract_code"), contract_title: form.get("contract_title"),
          employer: form.get("employer"), statement_title: form.get("statement_title"),
          amount_rials: form.get("amount_rials"), received_rials: 0, due_date: form.get("due_date"),
        }),
      });
      const payload = await response.json();
      if (response.status === 401 || response.status === 403) { setFinanceModal(false); setLoginModal(true); throw new Error("ابتدا وارد سامانه شوید"); }
      if (!response.ok) throw new Error("اطلاعات مالی معتبر نیست یا رکورد تکراری است");
      setFinanceRecords((items) => [mapApiReceivable(payload), ...items]);
      setFinanceModal(false); notify("مطالبه به‌صورت پیش‌نویس در PostgreSQL ثبت شد");
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت مطالبه انجام نشد");
    } finally { setSaving(false); }
  }

  async function submitPaymentReceipt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedReceivable?.recordId) return;
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/payment-receipts/`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({
          receivable: selectedReceivable.recordId, amount_rials: form.get("amount_rials"),
          received_date: form.get("received_date"), tracking_code: form.get("tracking_code"), note: form.get("note"),
        }),
      });
      const payload = await response.json();
      if (response.status === 401 || response.status === 403) { setReceiptModal(false); setLoginModal(true); throw new Error("ابتدا وارد سامانه شوید"); }
      if (!response.ok) throw new Error(payload.detail || "اطلاعات دریافت معتبر نیست");
      setReceiptModal(false); setSelectedReceivable(null); notify("دریافت وجه به‌صورت پیش‌نویس در PostgreSQL ثبت شد");
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت دریافت انجام نشد");
    } finally { setSaving(false); }
  }

  function openReceipt(item: Receivable) {
    if (financeMode === "auth") { setLoginModal(true); return; }
    if (financeMode !== "live" || !item.recordId) { notify("ثبت دائمی دریافت در نسخه سرور فعال است"); return; }
    setSelectedReceivable(item); setReceiptModal(true);
  }

  const title = nav.find((item) => item.id === page)?.label;

  return <main className="shell">
    <aside className={`sidebar ${menu ? "open" : ""}`}>
      <div className="brand"><b>P</b><div><strong>PDP One</strong><span>سامانه یکپارچه مدیریت</span></div><button className="mobile-close" onClick={() => setMenu(false)}>×</button></div>
      <p className="nav-label">فضای کاری</p>
      <nav>{nav.map((item) => <button key={item.id} onClick={() => navigate(item.id)} className={page === item.id ? "active" : ""}><i>{item.icon}</i>{item.label}{item.id === "tenders" && <em>۱۲</em>}</button>)}</nav>
      <div className="spacer" />
      <section className="assistant-card"><span>✦</span><strong>دستیار هوشمند PDP</strong><p>تحلیل داده‌ها و ثبت اطلاعات از طریق ChatGPT</p><button onClick={() => navigate("analysis")}>ورود به مرکز تحلیل ←</button></section>
      <footer><b>م‌م</b><div><strong>محمد ملکی</strong><span>مدیر سامانه</span></div><i>•••</i></footer>
    </aside>
    {menu && <button className="overlay" onClick={() => setMenu(false)} aria-label="بستن منو" />}

    <section className="workspace">
      <header className="topbar">
        <div className="page-title"><button className="hamburger" onClick={() => setMenu(true)}>☰</button><div><h1>{title}</h1><span>جمعه، ۲۶ تیر ۱۴۰۵</span></div></div>
        <div className="actions"><label className="search"><span>⌕</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جست‌وجو در سامانه..." /></label><button className="bell">♢<i /></button><button className="primary" onClick={() => setModal(true)}>＋ ثبت قرارداد</button></div>
      </header>
      <div className="content">
        {page === "dashboard" && <Dashboard contracts={results} navigate={navigate} notify={notify} />}
        {page === "contracts" && <SectionIntro eyebrow="مدیریت قراردادها" title="پرونده قراردادهای شرکت" description="جست‌وجو، کنترل پیشرفت و پیگیری تعهدات قراردادی در یک نمای یکپارچه.">
          <div className="toolbar"><label className="search wide"><span>⌕</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره، عنوان یا کارفرما..." /></label><div className="pills"><button className="selected">همه {contracts.length}</button><button>فعال</button><button>بحرانی</button><button>پیش‌نویس</button></div><button className="primary" onClick={() => setModal(true)}>＋ قرارداد جدید</button></div>
          <div className="panel table-panel"><ContractTable contracts={results} detailed /></div>
        </SectionIntro>}
        {page === "finance" && <SectionIntro eyebrow="کنترل مالی پروژه‌ها" title="مالی و مطالبات" description="نمای یکپارچه صورت‌وضعیت‌ها، سررسیدها، مبالغ وصول‌شده و مطالبات نیازمند پیگیری.">
          <div className={`connection-banner ${financeMode}`}><i />{financeMode === "live" ? "متصل به پایگاه داده PostgreSQL" : financeMode === "auth" ? "برای مشاهده و ثبت داده واقعی وارد سامانه شوید" : financeMode === "loading" ? "در حال بررسی اتصال به سرور..." : "نسخه نمایشی؛ داده واقعی در نسخه سرور شرکت نگهداری می‌شود"}{financeMode === "auth" && <button onClick={() => setLoginModal(true)}>ورود کاربر</button>}</div>
          <section className="finance-stats">
            <article className="finance-stat open"><span>کل مطالبات باز</span><b>{financeSummary.openAmount}</b><small>میلیارد تومان</small><em>{numberFa.format(financeSummary.openCount)} پرونده در جریان</em></article>
            <article className="finance-stat overdue"><span>مطالبات معوق</span><b>{financeSummary.overdueAmount}</b><small>میلیارد تومان</small><em>نیازمند اقدام واحد مالی</em></article>
            <article className="finance-stat collected"><span>مجموع وصول‌شده</span><b>{financeSummary.collectedAmount}</b><small>میلیارد تومان</small><em>{financeMode === "live" ? "بر اساس داده ثبت‌شده" : "۱۴.۸٪ رشد"}</em></article>
            <article className="finance-stat upcoming"><span>سررسید نزدیک</span><b>{numberFa.format(financeSummary.dueSoonCount)}</b><small>صورت‌وضعیت</small><em>تا هفت روز آینده</em></article>
          </section>
          <div className="finance-toolbar">
            <label className="search wide"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="قرارداد، کارفرما یا صورت‌وضعیت..." /></label>
            <div className="pills" aria-label="فیلتر وضعیت مالی">{(["همه", "پیش‌نویس", "باز", "معوق", "سررسید نزدیک", "در انتظار تأیید", "وصول شده"] as FinanceFilter[]).map((filter) => <button key={filter} className={financeFilter === filter ? "selected" : ""} onClick={() => setFinanceFilter(filter)}>{filter}</button>)}</div>
            <button className="primary" onClick={() => financeMode === "live" ? setFinanceModal(true) : financeMode === "auth" ? setLoginModal(true) : notify("ثبت دائمی در نسخه سرور فعال است")}>＋ ثبت مطالبه</button>
          </div>
          <div className="panel finance-panel"><ReceivablesTable items={receivables} onReceipt={openReceipt} /></div>
        </SectionIntro>}
        {page === "projects" && <SectionIntro eyebrow="مدیریت پروژه" title="پروژه‌های جاری" description="پایش پیشرفت، تیم مسئول، مدارک و وضعیت مالی پروژه‌ها."><div className="cards-grid">{seedContracts.slice(0,3).map((item, i) => <article className="panel project-card" key={item.id}><div className="project-head"><b className={`project-icon i${i}`}>◇</b><span className={statusClass(item.status)}>{item.status}</span></div><small>{item.field}</small><h3>{item.title}</h3><p>{item.employer}</p><div className="progress"><div><b>پیشرفت پروژه</b><em>{item.progress}٪</em></div><span><i style={{width:`${item.progress}%`}} /></span></div><button onClick={() => notify(`پرونده ${item.id} انتخاب شد`)}>مشاهده پرونده ←</button></article>)}</div></SectionIntro>}
        {page === "tenders" && <SectionIntro eyebrow="پایش فرصت‌ها" title="مناقصات پیشنهادی برای PDP" description="آگهی‌های جمع‌آوری‌شده پس از حذف موارد تکراری و تطبیق با صلاحیت‌های شرکت."><div className="tender-stats"><article><b>۴۷</b><span>آگهی جدید امروز</span></article><article><b>۱۲</b><span>دارای تطابق بالا</span></article><article><b>۵</b><span>مهلت کمتر از ۷ روز</span></article></div><div className="panel opportunities">{["مطالعات توسعه منطقه ویژه اقتصادی","طراحی مجموعه آموزشی و ورزشی","مطالعات برنامه‌ریزی فضایی شهرستان"].map((item,i)=><article key={item}><div className="score"><b>{[92,84,78][i]}٪</b><span>تطابق</span></div><div><small>{["ستاد ایران","هزاره","پارس‌نماد"][i]}</small><h3>{item}</h3><p>{["سازمان منطقه ویژه اقتصادی","اداره کل نوسازی مدارس","سازمان مدیریت و برنامه‌ریزی"][i]}</p></div><div className="opp-action"><span>مهلت: {[3,6,9][i]} روز</span><button onClick={()=>notify("فرصت به فهرست بررسی افزوده شد")}>افزودن به بررسی</button></div></article>)}</div></SectionIntro>}
        {page === "analysis" && <SectionIntro eyebrow="مرکز هوشمندی" title="تحلیل‌های ChatGPT" description="تحلیل‌های ذخیره‌شده با ذکر داده‌های منبع، زمان تولید و وضعیت بازبینی انسانی."><div className="panel analysis-hero"><b>✦</b><div><span>اتصال آزمایشی</span><h3>از ChatGPT بخواهید داده‌های PDP One را تحلیل کند</h3><p>ابزار MCP اطلاعات مجاز را از API می‌خواند و نتیجه قابل بازبینی را در همین صفحه ذخیره می‌کند.</p></div><button className="primary" onClick={()=>notify("درخواست نمونه آماده شد")}>ساخت درخواست نمونه</button></div><div className="cards-grid">{["ریسک وصول مطالبات","فرصت مناقصه پیشنهادی","کنترل برنامه زمان‌بندی"].map((item,i)=><article className="panel report" key={item}><div><span>گزارش AI-{1405120+i}</span><em>بازبینی شده</em></div><h3>{item}</h3><p>{["سه قرارداد در مجموع ۹.۷ میلیارد تومان مطالبات با تأخیر بیش از ۳۰ روز دارند.","مناقصه مطالعات توسعه منطقه ویژه با صلاحیت‌های شرکت تطابق بالایی دارد.","دو پروژه در مسیر بحرانی قرار گرفته‌اند و یک تحویل کلیدی در هفت روز آینده دارند."][i]}</p><footer><span>منبع: {i+3} رکورد سامانه</span><button onClick={()=>notify(item)}>مشاهده گزارش ←</button></footer></article>)}</div></SectionIntro>}
      </div>
    </section>

    {modal && <div className="modal-layer" onMouseDown={(e)=>e.currentTarget===e.target&&setModal(false)}><section className="modal" role="dialog" aria-modal="true"><header><div><small>ثبت سریع</small><h2>پیش‌نویس قرارداد جدید</h2></div><button onClick={()=>setModal(false)}>×</button></header><p>اطلاعات اولیه را وارد کنید. تأیید نهایی بعداً از داخل پرونده انجام می‌شود.</p><form onSubmit={submit}><label className="full">عنوان قرارداد *<input name="title" required autoFocus placeholder="مثلاً مطالعات طرح جامع..." /></label><label className="full">کارفرما *<input name="employer" required placeholder="نام دستگاه یا شرکت کارفرما" /></label><label>حوزه تخصصی<select name="field"><option>معماری</option><option>برنامه‌ریزی فضایی</option><option>تاسیسات</option><option>انرژی</option></select></label><label>مبلغ اولیه (میلیارد تومان)<input name="value" inputMode="decimal" placeholder="۰" /></label><div className="modal-note full"><b>i</b>این رکورد با وضعیت پیش‌نویس ثبت می‌شود و اثر مالی ندارد.</div><footer className="full"><button type="button" onClick={()=>setModal(false)}>انصراف</button><button className="primary">ثبت پیش‌نویس</button></footer></form></section></div>}
    {loginModal && <div className="modal-layer" onMouseDown={(e)=>e.currentTarget===e.target&&setLoginModal(false)}><section className="modal compact" role="dialog" aria-modal="true"><header><div><small>دسترسی امن</small><h2>ورود به PDP One</h2></div><button onClick={()=>setLoginModal(false)}>×</button></header><p>با حسابی که هنگام نصب ساخته‌اید وارد شوید.</p><form onSubmit={submitLogin}><label className="full">نام کاربری<input name="username" required autoFocus autoComplete="username" /></label><label className="full">رمز عبور<input name="password" type="password" required autoComplete="current-password" /></label><footer className="full"><button type="button" onClick={()=>setLoginModal(false)}>انصراف</button><button className="primary" disabled={saving}>{saving ? "در حال ورود..." : "ورود"}</button></footer></form></section></div>}
    {financeModal && <div className="modal-layer" onMouseDown={(e)=>e.currentTarget===e.target&&setFinanceModal(false)}><section className="modal" role="dialog" aria-modal="true"><header><div><small>ثبت مالی کنترل‌شده</small><h2>پیش‌نویس مطالبه جدید</h2></div><button onClick={()=>setFinanceModal(false)}>×</button></header><p>رکورد پس از ذخیره نیازمند بازبینی و تأیید واحد مالی است.</p><form onSubmit={submitReceivable}><label>کد قرارداد *<input name="contract_code" required autoFocus placeholder="PDP-1405-012" /></label><label>عنوان صورت‌وضعیت *<input name="statement_title" required placeholder="صورت‌وضعیت شماره ۶" /></label><label className="full">عنوان قرارداد *<input name="contract_title" required /></label><label className="full">کارفرما *<input name="employer" required /></label><label>مبلغ (ریال) *<input name="amount_rials" type="number" min="1" required inputMode="numeric" /></label><label>تاریخ سررسید *<input name="due_date" type="date" required /></label><div className="modal-note full"><b>i</b>ChatGPT و رابط وب فقط پیش‌نویس می‌سازند؛ تأیید مالی خودکار انجام نمی‌شود.</div><footer className="full"><button type="button" onClick={()=>setFinanceModal(false)}>انصراف</button><button className="primary" disabled={saving}>{saving ? "در حال ذخیره..." : "ثبت در پایگاه داده"}</button></footer></form></section></div>}
    {receiptModal && selectedReceivable && <div className="modal-layer" onMouseDown={(e)=>e.currentTarget===e.target&&setReceiptModal(false)}><section className="modal compact" role="dialog" aria-modal="true"><header><div><small>ثبت دریافت کنترل‌شده</small><h2>دریافت وجه جدید</h2></div><button onClick={()=>setReceiptModal(false)}>×</button></header><p>{selectedReceivable.statement} · {selectedReceivable.contractId}</p><form onSubmit={submitPaymentReceipt}><label className="full">مبلغ دریافت (ریال) *<input name="amount_rials" type="number" min="1" required autoFocus inputMode="numeric" /></label><label className="full">تاریخ دریافت *<input name="received_date" type="date" required /></label><label className="full">شماره پیگیری بانکی<input name="tracking_code" /></label><label className="full">توضیحات<textarea name="note" rows={3} /></label><div className="modal-note full"><b>i</b>این دریافت تا تأیید واحد مالی، روی مبلغ وصول‌شده نهایی اثر نمی‌گذارد.</div><footer className="full"><button type="button" onClick={()=>setReceiptModal(false)}>انصراف</button><button className="primary" disabled={saving}>{saving ? "در حال ذخیره..." : "ثبت پیش‌نویس دریافت"}</button></footer></form></section></div>}
    {toast && <div className="toast"><b>✓</b>{toast}</div>}
  </main>;
}

function Dashboard({contracts,navigate,notify}:{contracts:Contract[];navigate:(p:Page)=>void;notify:(m:string)=>void}) {
  return <><section className="welcome"><div><small>نمای کلی شرکت</small><h2>سلام، امروز چه چیزی نیاز به توجه دارد؟</h2><p>وضعیت قراردادها، مطالبات و فرصت‌های جدید بر اساس آخرین اطلاعات ثبت‌شده.</p></div><span><i /> آخرین به‌روزرسانی: ۱۹:۴۲</span></section>
    <section className="stats">{stats.map(([label,value,note,tone])=><article className={`stat ${tone}`} key={label}><header><span>{label}</span><i /></header><b>{value}</b><p>{note}</p></article>)}</section>
    <section className="dashboard-grid"><article className="panel chart"><header><div><small>نمای مالی</small><h3>وصول مطالبات شش‌ماهه</h3></div><button onClick={()=>navigate("finance")}>جزئیات مالی ←</button></header><div className="chart-total"><b>۴۸.۲ میلیارد</b><span>٪۱۴.۸ رشد نسبت به دوره قبل</span></div><div className="bars">{[42,58,51,74,62,86].map((h,i)=><div key={i}><span><i style={{height:`${h}%`}} /></span><small>{["بهمن","اسفند","فروردین","اردیبهشت","خرداد","تیر"][i]}</small></div>)}</div></article>
    <article className="panel alerts"><header><div><small>اقدام لازم</small><h3>موارد نیازمند توجه</h3></div><button onClick={()=>notify("همه اعلان‌ها در نسخه بعدی نمایش داده می‌شود")}>مشاهده همه</button></header>{["مهلت ارسال پیشنهاد مناقصه قزوین","صورت‌وضعیت شماره ۶ تأیید نشده است","بیمه‌نامه قرارداد بیمارستان رو به انقضاست"].map((x,i)=><button className="alert" key={x} onClick={()=>notify(x)}><i className={`dot d${i}`} /><span><b>{x}</b><small>{["تا ۲ روز دیگر · واحد مناقصات","پروژه صفادشت · ۱۸ روز تأخیر","۵ مرداد ۱۴۰۵ · واحد قراردادها"][i]}</small></span><em>{["فوری","پیگیری","هشدار"][i]}</em></button>)}</article></section>
    <section className="dashboard-grid lower"><article className="panel contracts"><header><div><small>عملکرد اجرایی</small><h3>قراردادهای در جریان</h3></div><button onClick={()=>navigate("contracts")}>همه قراردادها ←</button></header><ContractTable contracts={contracts.slice(0,3)} /></article><article className="panel insights"><header><div><small>✦ تحلیل ChatGPT</small><h3>بینش‌های تازه</h3></div><em>فعال</em></header><div className="insight warning"><b>ریسک وصول مطالبات</b><p>سه قرارداد، مطالبات با تأخیر بیش از ۳۰ روز دارند.</p><button onClick={()=>navigate("finance")}>مشاهده مطالبات و منابع ←</button></div><div className="insight success"><b>فرصت مناقصه پیشنهادی</b><p>یک فرصت جدید با صلاحیت‌های شرکت تطابق بالایی دارد.</p><button onClick={()=>navigate("tenders")}>بررسی فرصت ←</button></div></article></section></>;
}

function SectionIntro({eyebrow,title,description,children}:{eyebrow:string;title:string;description:string;children:React.ReactNode}) { return <><section className="intro"><small>{eyebrow}</small><h2>{title}</h2><p>{description}</p></section>{children}</>; }

function ContractTable({contracts,detailed=false}:{contracts:Contract[];detailed?:boolean}) { return <div className="table-wrap"><table><thead><tr><th>قرارداد و کارفرما</th><th>حوزه</th><th>مبلغ</th>{detailed&&<th>سررسید</th>}<th>پیشرفت</th><th>وضعیت</th><th /></tr></thead><tbody>{contracts.map(c=><tr key={c.id}><td><b>{c.title}</b><small>{c.id} · {c.employer}</small></td><td>{c.field}</td><td>{c.value}</td>{detailed&&<td>{c.due}</td>}<td><div className="mini-progress"><span><i style={{width:`${c.progress}%`}} /></span><em>{c.progress}٪</em></div></td><td><span className={statusClass(c.status)}>{c.status}</span></td><td>←</td></tr>)}</tbody></table>{!contracts.length&&<p className="empty">رکوردی پیدا نشد.</p>}</div>; }

function ReceivablesTable({items,onReceipt}:{items:Receivable[];onReceipt:(item:Receivable)=>void}) { return <div className="table-wrap"><table><thead><tr><th>قرارداد و کارفرما</th><th>صورت‌وضعیت</th><th>مبلغ</th><th>وصول‌شده</th><th>سررسید</th><th>وضعیت</th><th /></tr></thead><tbody>{items.map((item)=><tr key={item.id}><td><b>{item.title}</b><small>{item.contractId} · {item.employer}</small></td><td><b>{item.statement}</b><small>{item.id}</small></td><td className="money">{item.amount}</td><td className="money received">{item.received}</td><td>{item.due}</td><td><span className={financeStatusClass(item.status)}>{item.status}</span></td><td><button className="row-action" onClick={()=>onReceipt(item)} aria-label={`ثبت دریافت برای ${item.id}`}>＋</button></td></tr>)}</tbody></table>{!items.length&&<p className="empty">موردی با این فیلتر پیدا نشد.</p>}</div>; }
