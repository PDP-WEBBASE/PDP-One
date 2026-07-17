"use client";

import { FormEvent, useMemo, useState } from "react";

type Page = "dashboard" | "contracts" | "projects" | "tenders" | "analysis";
type Status = "فعال" | "در انتظار" | "بحرانی" | "پیش‌نویس";
type Contract = { id: string; title: string; employer: string; field: string; value: string; progress: number; status: Status; due: string };

const seedContracts: Contract[] = [
  { id: "PDP-1405-012", title: "مطالعات طرح جامع شهرک صنعتی صفادشت", employer: "شرکت شهرک‌های صنعتی تهران", field: "برنامه‌ریزی فضایی", value: "۱۲.۸ میلیارد", progress: 72, status: "فعال", due: "۲۸ مرداد ۱۴۰۵" },
  { id: "PDP-1405-009", title: "طراحی معماری مجموعه اداری مرکزی", employer: "سازمان منطقه آزاد", field: "معماری", value: "۸.۴ میلیارد", progress: 48, status: "در انتظار", due: "۱۲ شهریور ۱۴۰۵" },
  { id: "PDP-1404-031", title: "خدمات مشاور تاسیسات مکانیکی بیمارستان", employer: "دانشگاه علوم پزشکی", field: "تاسیسات", value: "۵.۹ میلیارد", progress: 89, status: "بحرانی", due: "۵ مرداد ۱۴۰۵" },
  { id: "PDP-1405-015", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی آفتاب", field: "انرژی", value: "۳.۶ میلیارد", progress: 16, status: "فعال", due: "۲۲ آبان ۱۴۰۵" },
];

const nav: { id: Page; label: string; icon: string }[] = [
  { id: "dashboard", label: "داشبورد مدیریت", icon: "◫" },
  { id: "contracts", label: "قراردادها", icon: "▤" },
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

export default function Home() {
  const [page, setPage] = useState<Page>("dashboard");
  const [menu, setMenu] = useState(false);
  const [modal, setModal] = useState(false);
  const [search, setSearch] = useState("");
  const [contracts, setContracts] = useState(seedContracts);
  const [toast, setToast] = useState("");
  const results = useMemo(() => contracts.filter((c) => !search || [c.id, c.title, c.employer, c.field].some((v) => v.includes(search))), [contracts, search]);

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
        {page === "projects" && <SectionIntro eyebrow="مدیریت پروژه" title="پروژه‌های جاری" description="پایش پیشرفت، تیم مسئول، مدارک و وضعیت مالی پروژه‌ها."><div className="cards-grid">{seedContracts.slice(0,3).map((item, i) => <article className="panel project-card" key={item.id}><div className="project-head"><b className={`project-icon i${i}`}>◇</b><span className={statusClass(item.status)}>{item.status}</span></div><small>{item.field}</small><h3>{item.title}</h3><p>{item.employer}</p><div className="progress"><div><b>پیشرفت پروژه</b><em>{item.progress}٪</em></div><span><i style={{width:`${item.progress}%`}} /></span></div><button onClick={() => notify(`پرونده ${item.id} انتخاب شد`)}>مشاهده پرونده ←</button></article>)}</div></SectionIntro>}
        {page === "tenders" && <SectionIntro eyebrow="پایش فرصت‌ها" title="مناقصات پیشنهادی برای PDP" description="آگهی‌های جمع‌آوری‌شده پس از حذف موارد تکراری و تطبیق با صلاحیت‌های شرکت."><div className="tender-stats"><article><b>۴۷</b><span>آگهی جدید امروز</span></article><article><b>۱۲</b><span>دارای تطابق بالا</span></article><article><b>۵</b><span>مهلت کمتر از ۷ روز</span></article></div><div className="panel opportunities">{["مطالعات توسعه منطقه ویژه اقتصادی","طراحی مجموعه آموزشی و ورزشی","مطالعات برنامه‌ریزی فضایی شهرستان"].map((item,i)=><article key={item}><div className="score"><b>{[92,84,78][i]}٪</b><span>تطابق</span></div><div><small>{["ستاد ایران","هزاره","پارس‌نماد"][i]}</small><h3>{item}</h3><p>{["سازمان منطقه ویژه اقتصادی","اداره کل نوسازی مدارس","سازمان مدیریت و برنامه‌ریزی"][i]}</p></div><div className="opp-action"><span>مهلت: {[3,6,9][i]} روز</span><button onClick={()=>notify("فرصت به فهرست بررسی افزوده شد")}>افزودن به بررسی</button></div></article>)}</div></SectionIntro>}
        {page === "analysis" && <SectionIntro eyebrow="مرکز هوشمندی" title="تحلیل‌های ChatGPT" description="تحلیل‌های ذخیره‌شده با ذکر داده‌های منبع، زمان تولید و وضعیت بازبینی انسانی."><div className="panel analysis-hero"><b>✦</b><div><span>اتصال آزمایشی</span><h3>از ChatGPT بخواهید داده‌های PDP One را تحلیل کند</h3><p>ابزار MCP اطلاعات مجاز را از API می‌خواند و نتیجه قابل بازبینی را در همین صفحه ذخیره می‌کند.</p></div><button className="primary" onClick={()=>notify("درخواست نمونه آماده شد")}>ساخت درخواست نمونه</button></div><div className="cards-grid">{["ریسک وصول مطالبات","فرصت مناقصه پیشنهادی","کنترل برنامه زمان‌بندی"].map((item,i)=><article className="panel report" key={item}><div><span>گزارش AI-{1405120+i}</span><em>بازبینی شده</em></div><h3>{item}</h3><p>{["سه قرارداد در مجموع ۹.۷ میلیارد تومان مطالبات با تأخیر بیش از ۳۰ روز دارند.","مناقصه مطالعات توسعه منطقه ویژه با صلاحیت‌های شرکت تطابق بالایی دارد.","دو پروژه در مسیر بحرانی قرار گرفته‌اند و یک تحویل کلیدی در هفت روز آینده دارند."][i]}</p><footer><span>منبع: {i+3} رکورد سامانه</span><button onClick={()=>notify(item)}>مشاهده گزارش ←</button></footer></article>)}</div></SectionIntro>}
      </div>
    </section>

    {modal && <div className="modal-layer" onMouseDown={(e)=>e.currentTarget===e.target&&setModal(false)}><section className="modal" role="dialog" aria-modal="true"><header><div><small>ثبت سریع</small><h2>پیش‌نویس قرارداد جدید</h2></div><button onClick={()=>setModal(false)}>×</button></header><p>اطلاعات اولیه را وارد کنید. تأیید نهایی بعداً از داخل پرونده انجام می‌شود.</p><form onSubmit={submit}><label className="full">عنوان قرارداد *<input name="title" required autoFocus placeholder="مثلاً مطالعات طرح جامع..." /></label><label className="full">کارفرما *<input name="employer" required placeholder="نام دستگاه یا شرکت کارفرما" /></label><label>حوزه تخصصی<select name="field"><option>معماری</option><option>برنامه‌ریزی فضایی</option><option>تاسیسات</option><option>انرژی</option></select></label><label>مبلغ اولیه (میلیارد تومان)<input name="value" inputMode="decimal" placeholder="۰" /></label><div className="modal-note full"><b>i</b>این رکورد با وضعیت پیش‌نویس ثبت می‌شود و اثر مالی ندارد.</div><footer className="full"><button type="button" onClick={()=>setModal(false)}>انصراف</button><button className="primary">ثبت پیش‌نویس</button></footer></form></section></div>}
    {toast && <div className="toast"><b>✓</b>{toast}</div>}
  </main>;
}

function Dashboard({contracts,navigate,notify}:{contracts:Contract[];navigate:(p:Page)=>void;notify:(m:string)=>void}) {
  return <><section className="welcome"><div><small>نمای کلی شرکت</small><h2>سلام، امروز چه چیزی نیاز به توجه دارد؟</h2><p>وضعیت قراردادها، مطالبات و فرصت‌های جدید بر اساس آخرین اطلاعات ثبت‌شده.</p></div><span><i /> آخرین به‌روزرسانی: ۱۹:۴۲</span></section>
    <section className="stats">{stats.map(([label,value,note,tone])=><article className={`stat ${tone}`} key={label}><header><span>{label}</span><i /></header><b>{value}</b><p>{note}</p></article>)}</section>
    <section className="dashboard-grid"><article className="panel chart"><header><div><small>نمای مالی</small><h3>وصول مطالبات شش‌ماهه</h3></div><select><option>شش ماه اخیر</option></select></header><div className="chart-total"><b>۴۸.۲ میلیارد</b><span>٪۱۴.۸ رشد نسبت به دوره قبل</span></div><div className="bars">{[42,58,51,74,62,86].map((h,i)=><div key={i}><span><i style={{height:`${h}%`}} /></span><small>{["بهمن","اسفند","فروردین","اردیبهشت","خرداد","تیر"][i]}</small></div>)}</div></article>
    <article className="panel alerts"><header><div><small>اقدام لازم</small><h3>موارد نیازمند توجه</h3></div><button onClick={()=>notify("همه اعلان‌ها در نسخه بعدی نمایش داده می‌شود")}>مشاهده همه</button></header>{["مهلت ارسال پیشنهاد مناقصه قزوین","صورت‌وضعیت شماره ۶ تأیید نشده است","بیمه‌نامه قرارداد بیمارستان رو به انقضاست"].map((x,i)=><button className="alert" key={x} onClick={()=>notify(x)}><i className={`dot d${i}`} /><span><b>{x}</b><small>{["تا ۲ روز دیگر · واحد مناقصات","پروژه صفادشت · ۱۸ روز تأخیر","۵ مرداد ۱۴۰۵ · واحد قراردادها"][i]}</small></span><em>{["فوری","پیگیری","هشدار"][i]}</em></button>)}</article></section>
    <section className="dashboard-grid lower"><article className="panel contracts"><header><div><small>عملکرد اجرایی</small><h3>قراردادهای در جریان</h3></div><button onClick={()=>navigate("contracts")}>همه قراردادها ←</button></header><ContractTable contracts={contracts.slice(0,3)} /></article><article className="panel insights"><header><div><small>✦ تحلیل ChatGPT</small><h3>بینش‌های تازه</h3></div><em>فعال</em></header><div className="insight warning"><b>ریسک وصول مطالبات</b><p>سه قرارداد، مطالبات با تأخیر بیش از ۳۰ روز دارند.</p><button onClick={()=>navigate("analysis")}>مشاهده تحلیل و منابع ←</button></div><div className="insight success"><b>فرصت مناقصه پیشنهادی</b><p>یک فرصت جدید با صلاحیت‌های شرکت تطابق بالایی دارد.</p><button onClick={()=>navigate("tenders")}>بررسی فرصت ←</button></div></article></section></>;
}

function SectionIntro({eyebrow,title,description,children}:{eyebrow:string;title:string;description:string;children:React.ReactNode}) { return <><section className="intro"><small>{eyebrow}</small><h2>{title}</h2><p>{description}</p></section>{children}</>; }

function ContractTable({contracts,detailed=false}:{contracts:Contract[];detailed?:boolean}) { return <div className="table-wrap"><table><thead><tr><th>قرارداد و کارفرما</th><th>حوزه</th><th>مبلغ</th>{detailed&&<th>سررسید</th>}<th>پیشرفت</th><th>وضعیت</th><th /></tr></thead><tbody>{contracts.map(c=><tr key={c.id}><td><b>{c.title}</b><small>{c.id} · {c.employer}</small></td><td>{c.field}</td><td>{c.value}</td>{detailed&&<td>{c.due}</td>}<td><div className="mini-progress"><span><i style={{width:`${c.progress}%`}} /></span><em>{c.progress}٪</em></div></td><td><span className={statusClass(c.status)}>{c.status}</span></td><td>←</td></tr>)}</tbody></table>{!contracts.length&&<p className="empty">رکوردی پیدا نشد.</p>}</div>; }
