"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./workspace-v2.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "prompts" | "keywords" | "company" | "versions";
type UrgencyTone = "critical" | "high" | "medium" | "normal" | "unknown";
type LockSection = "schedule" | "prompts" | "keywords" | "company";
type FileCategory = "prompt_reference" | "keywords" | "company_profile" | "qualifications" | "resume";

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

type DirectReferral = {
  id: string;
  title: string;
  employer: string;
  province: string;
  type: string;
  stage: "new" | "reviewing" | "selected" | "preparing" | "submitted" | "won" | "lost" | "stopped";
  responsible: string;
  nextAction: string;
  nextActionDue: string | null;
  probability: number;
};

type Source = {
  id: string;
  name: string;
  enabled: boolean;
  status_label: string;
  connectors: { id: string; key: string; notice_type_label: string; enabled: boolean; status_label: string }[];
};

type AutomationSettings = {
  id: string;
  enabled: boolean;
  cadence: "hourly" | "daily";
  cadence_label: string;
  interval_minutes: number;
  daily_time: string | null;
  timezone_name: string;
  analysis_delay_minutes: number;
  scheduled_task_enabled: boolean;
  manual_command: string;
};

type AnalysisContext = {
  id: string;
  version: number;
  status: "draft" | "active" | "retired";
  status_label: string;
  role_text: string;
  base_instructions: string;
  analysis_prompt?: string;
  tender_prompt?: string;
  inquiry_prompt?: string;
  company_profile: Record<string, unknown>;
  qualifications: unknown[];
  keywords: Record<string, unknown>;
  experience_summary: unknown[];
  attachments?: { id: string; category: string; category_label: string; original_name: string; size_bytes: number }[];
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
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
  { id: "D1", title: "رایزنی طرح توسعه پردیس اداری", employer: "گروه سرمایه‌گذاری پارس", province: "تهران", type: "رایزنی با کارفرما", stage: "reviewing", responsible: "محمد ملکی", nextAction: "ارسال معرفی‌نامه سوابق", nextActionDue: "2026-07-23T11:00:00+03:30", probability: 70 },
  { id: "D2", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer: "شرکت انرژی نو", province: "یزد", type: "معرفی مستقیم", stage: "selected", responsible: "توسعه کسب‌وکار", nextAction: "هماهنگی جلسه فنی", nextActionDue: "2026-07-25T10:00:00+03:30", probability: 55 },
  { id: "D3", title: "دعوت محدود طراحی مجموعه درمانی", employer: "بنیاد توسعه سلامت", province: "تهران", type: "دعوت محدود", stage: "submitted", responsible: "مدیر فنی", nextAction: "پیگیری دریافت پیشنهاد", nextActionDue: "2026-07-24T09:00:00+03:30", probability: 80 },
  { id: "D4", title: "طراحی مرکز خدمات شهری", employer: "شرکت عمران شهری", province: "البرز", type: "مذاکره مستقیم", stage: "won", responsible: "مدیرعامل", nextAction: "ایجاد پیش‌نویس قرارداد", nextActionDue: "2026-07-26T10:00:00+03:30", probability: 100 },
];

const seedSources: Source[] = [
  { id: "S1", name: "هزاره", enabled: true, status_label: "فعال", connectors: [{ id: "C1", key: "hezareh_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده" }, { id: "C2", key: "hezareh_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده" }] },
  { id: "S2", name: "پارس نماد داده", enabled: true, status_label: "فعال", connectors: [{ id: "C3", key: "parsnamad_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده" }, { id: "C4", key: "parsnamad_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده" }] },
  { id: "S3", name: "ستاد ایران", enabled: false, status_label: "موقتاً تعلیق‌شده / نیازمند بررسی مجدد در ساعت دسترسی", connectors: [{ id: "C5", key: "setad_tenders", notice_type_label: "مناقصات", enabled: false, status_label: "نیازمند بررسی" }, { id: "C6", key: "setad_inquiries", notice_type_label: "استعلامات", enabled: false, status_label: "نیازمند بررسی" }] },
];

const seedAutomation: AutomationSettings = { id: "A1", enabled: false, cadence: "daily", cadence_label: "روزانه", interval_minutes: 60, daily_time: "17:00", timezone_name: "Asia/Tehran", analysis_delay_minutes: 60, scheduled_task_enabled: true, manual_command: "PDP" };
const seedContext: AnalysisContext = { id: "CTX12", version: 12, status: "active", status_label: "فعال", role_text: "تحلیلگر ارشد مناقصات، استعلامات و ارجاعات مستقیم شرکت مهندسین مشاور طرح و برنامه پارس", base_instructions: "تحلیل بر اساس صلاحیت، ظرفیت، زمان، ریسک و سوابق انجام شود و نتیجه فقط پیش‌نویس باشد.", analysis_prompt: "هر فرصت را از نظر تناسب با شرکت، زمان باقی‌مانده، شرایط، ریسک، سوابق مرتبط، ظرفیت پاسخ و اقدام پیشنهادی تحلیل کن.", tender_prompt: "", inquiry_prompt: "", company_profile: { summary: "شرکت مهندسین مشاور طرح و برنامه پارس؛ فعال در معماری، شهرسازی، تأسیسات و برنامه‌ریزی فضایی." }, qualifications: ["رتبه ۳ معماری", "رتبه ۳ شهرسازی", "رتبه ۳ تأسیسات برق و مکانیک"], keywords: { active: ["طراحی معماری", "نظارت", "طرح جامع", "امکان‌سنجی"], excluded: ["تأمین کالا", "اجرای صرف"] }, experience_summary: ["پروژه‌های اداری و آموزشی", "مطالعات شهری و منطقه‌ای", "مطالعات امکان‌سنجی"], attachments: [] };

const tabs: [Tab, string][] = [["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"], ["direct", "ارجاعات مستقیم"], ["management", "مدیریت زیرسامانه"]];
const views: [WorkflowView, string][] = [["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"], ["submitted", "ارسال‌شده"], ["results", "نتایج"]];
const managementTabs: [ManagementView, string][] = [["extraction", "استخراج و منابع"], ["prompts", "نقش و Prompt"], ["keywords", "کلیدواژه‌ها"], ["company", "پروفایل، صلاحیت و رزومه"], ["versions", "نسخه‌ها و فعال‌سازی"]];

function listOf<T>(value: T[] | { results?: T[] }): T[] { return Array.isArray(value) ? value : value.results || []; }
function contextEditor(context: AnalysisContext): ContextEditor {
  const keywords = context.keywords || {};
  const active = Array.isArray(keywords.active) ? keywords.active : [];
  const excluded = Array.isArray(keywords.excluded) ? keywords.excluded : [];
  return {
    role: context.role_text || "",
    base: context.base_instructions || "",
    prompt: context.analysis_prompt || context.tender_prompt || context.inquiry_prompt || "",
    activeKeywords: active.join("\n"),
    excludedKeywords: excluded.join("\n"),
    companyProfile: String(context.company_profile?.summary || ""),
    qualifications: context.qualifications.map(String).join("\n"),
    experience: context.experience_summary.map(String).join("\n"),
  };
}
function urgency(value: string | null) {
  if (!value) return { tone: "unknown" as UrgencyTone, label: "تاریخ نامشخص", remaining: "نامشخص" };
  const hours = Math.ceil((new Date(value).getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone: "critical" as UrgencyTone, label: "مهلت گذشته", remaining: `${fa.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone: "critical" as UrgencyTone, label: "فوریت بحرانی", remaining: `${fa.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone: "high" as UrgencyTone, label: "فوریت زیاد", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  if (hours <= 168) return { tone: "medium" as UrgencyTone, label: "فوریت متوسط", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  return { tone: "normal" as UrgencyTone, label: "عادی", remaining: `${fa.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
}
function urgencyClass(tone: UrgencyTone) { return styles[tone]; }
function noticeMatches(item: Notice, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return item.recommended && !item.stage;
  if (view === "selected") return item.stage === "selected" || item.stage === "preparing";
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "results";
}
function directMatches(item: DirectReferral, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return ["new", "reviewing"].includes(item.stage);
  if (view === "selected") return ["selected", "preparing"].includes(item.stage);
  if (view === "submitted") return item.stage === "submitted";
  return ["won", "lost", "stopped"].includes(item.stage);
}
async function csrf() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include" });
  if (!response.ok) throw new Error("نشست کاربر دریافت نشد.");
  return String((await response.json()).csrf_token);
}

export default function ProcurementWorkspaceV2() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [notices, setNotices] = useState(seedNotices);
  const [direct, setDirect] = useState(seedDirect);
  const [sources, setSources] = useState(seedSources);
  const [automation, setAutomation] = useState(seedAutomation);
  const [contexts, setContexts] = useState<AnalysisContext[]>([seedContext]);
  const [editor, setEditor] = useState(contextEditor(seedContext));
  const [editing, setEditing] = useState<Record<LockSection, boolean>>({ schedule: false, prompts: false, keywords: false, company: false });
  const [files, setFiles] = useState<Record<FileCategory, File[]>>({ prompt_reference: [], keywords: [], company_profile: [], qualifications: [], resume: [] });
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<{ title: string; employer: string; status: string; details: string; deadline: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [sourceResponse, automationResponse, contextResponse] = await Promise.all([
          fetch(`${API_BASE}/procurement/sources/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/automation-settings/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/analysis-contexts/`, { credentials: "include" }),
        ]);
        if (![sourceResponse, automationResponse, contextResponse].every((response) => response.ok)) return;
        const [sourceData, automationData, contextData] = await Promise.all([sourceResponse.json(), automationResponse.json(), contextResponse.json()]);
        if (cancelled) return;
        const liveContexts = listOf<AnalysisContext>(contextData);
        const active = liveContexts.find((item) => item.status === "active") || liveContexts[0];
        setSources(listOf<Source>(sourceData));
        setAutomation(listOf<AutomationSettings>(automationData)[0] || seedAutomation);
        if (liveContexts.length) setContexts(liveContexts);
        if (active) setEditor(contextEditor(active));
        setMode("live");
      } catch { /* Preview falls back to safe local data. */ }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const activeContext = useMemo(() => contexts.find((item) => item.status === "active") || contexts[0] || seedContext, [contexts]);
  const draftContexts = useMemo(() => contexts.filter((item) => item.status === "draft"), [contexts]);
  const filteredNotices = useMemo(() => notices.filter((item) => {
    const kindMatches = tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry";
    return kindMatches && noticeMatches(item, noticeView) && (!search || `${item.title} ${item.employer} ${item.province}`.includes(search));
  }), [notices, noticeView, search, tab]);
  const filteredDirect = useMemo(() => direct.filter((item) => directMatches(item, directView) && (!search || `${item.title} ${item.employer} ${item.province}`.includes(search))), [direct, directView, search]);

  const stats = useMemo(() => {
    const tender = notices.filter((item) => item.kind === "tender");
    const inquiry = notices.filter((item) => item.kind === "inquiry");
    const activeNotice = (items: Notice[]) => items.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).length;
    return [
      { label: "مناقصات", total: tender.length, active: activeNotice(tender), won: tender.filter((item) => item.result === "برنده").length },
      { label: "استعلامات", total: inquiry.length, active: activeNotice(inquiry), won: inquiry.filter((item) => item.result === "برنده").length },
      { label: "ارجاعات مستقیم", total: direct.length, active: direct.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).length, won: direct.filter((item) => item.stage === "won").length },
    ];
  }, [direct, notices]);
  const maxChart = Math.max(...stats.map((item) => item.total), 1);
  const activeTotal = stats.reduce((sum, item) => sum + item.active, 0);
  const totalWon = stats.reduce((sum, item) => sum + item.won, 0);
  const urgentCount = notices.filter((item) => ["critical", "high"].includes(urgency(item.deadline).tone) && item.stage !== "results").length;
  const activeCases = [...notices.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title, subtitle: `${item.kind === "tender" ? "مناقصه" : "استعلام"} · ${item.employer}`, stage: item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next: item.nextAction, deadline: item.deadline })), ...direct.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)).map((item) => ({ title: item.title, subtitle: `ارجاع مستقیم · ${item.employer}`, stage: item.stage === "submitted" ? "ارسال‌شده" : "منتخب", next: item.nextAction, deadline: item.nextActionDue }))];
  const donutValues = stats.map((item) => item.active);
  const donutTotal = Math.max(donutValues.reduce((a, b) => a + b, 0), 1);
  const p1 = donutValues[0] / donutTotal * 100;
  const p2 = donutValues[1] / donutTotal * 100;
  const donutBackground = `conic-gradient(#2d7582 0 ${p1}%, #d5a52f ${p1}% ${p1 + p2}%, #8d70a9 ${p1 + p2}% 100%)`;

  function notify(text: string) { setMessage(text); window.setTimeout(() => setMessage(""), 4200); }
  function setLock(section: LockSection, value: boolean) { setEditing((current) => ({ ...current, [section]: value })); }
  function updateNotice(id: string, change: Partial<Notice>) { setNotices((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }
  function recommendNotice(item: Notice) { updateNotice(item.id, { recommended: true }); notify("رکورد به فهرست پیشنهادی اضافه شد."); }
  function selectNotice(item: Notice) { updateNotice(item.id, { stage: "selected", responsible: item.responsible || "محمد ملکی", nextAction: "تعیین برنامه تهیه پیشنهاد", progress: 5 }); notify("رکورد به منتخب منتقل شد."); }
  function submitNotice(item: Notice) { updateNotice(item.id, { stage: "submitted", progress: 100, nextAction: "پیگیری نتیجه" }); notify("رکورد به ارسال‌شده منتقل شد."); }
  function resultNotice(item: Notice) { const result = window.prompt("نتیجه را وارد کنید:", "برنده"); if (!result) return; updateNotice(item.id, { stage: "results", result: result as Notice["result"], nextAction: result === "برنده" ? "ایجاد پیش‌نویس قرارداد" : "ثبت علت نتیجه" }); notify(result === "برنده" ? "برد ثبت شد؛ پیش‌نویس قرارداد در ماژول قراردادها ایجاد خواهد شد." : "نتیجه ثبت شد."); }
  function directLabel(stage: DirectReferral["stage"]) { return ({ new: "پیشنهادی", reviewing: "پیشنهادی", selected: "منتخب", preparing: "منتخب · در دست تهیه", submitted: "ارسال‌شده", won: "موفق", lost: "ناموفق", stopped: "متوقف‌شده" } as Record<string, string>)[stage]; }
  function updateDirect(id: string, change: Partial<DirectReferral>) { setDirect((items) => items.map((item) => item.id === id ? { ...item, ...change } : item)); }

  async function handleFiles(category: FileCategory, event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || []);
    setFiles((current) => ({ ...current, [category]: [...current[category], ...selectedFiles] }));
    const textFile = selectedFiles.find((file) => file.name.toLowerCase().endsWith(".txt") || file.name.toLowerCase().endsWith(".md"));
    if (textFile) {
      const text = await textFile.text();
      if (category === "keywords") setEditor((current) => ({ ...current, activeKeywords: text }));
      if (category === "resume") setEditor((current) => ({ ...current, experience: text }));
      if (category === "company_profile") setEditor((current) => ({ ...current, companyProfile: text }));
      if (category === "qualifications") setEditor((current) => ({ ...current, qualifications: text }));
      if (category === "prompt_reference") setEditor((current) => ({ ...current, prompt: text }));
    }
  }

  async function createDraft(category: FileCategory | null) {
    setBusy(true);
    try {
      const version = Math.max(...contexts.map((item) => item.version), 0) + 1;
      const payload = {
        version,
        status: "draft",
        role_text: editor.role,
        base_instructions: editor.base,
        analysis_prompt: editor.prompt,
        tender_prompt: editor.prompt,
        inquiry_prompt: editor.prompt,
        company_profile: { summary: editor.companyProfile },
        qualifications: editor.qualifications.split("\n").map((value) => value.trim()).filter(Boolean),
        keywords: { active: editor.activeKeywords.split("\n").map((value) => value.trim()).filter(Boolean), excluded: editor.excludedKeywords.split("\n").map((value) => value.trim()).filter(Boolean) },
        experience_summary: editor.experience.split("\n").map((value) => value.trim()).filter(Boolean),
        component_versions: { role: version, prompt: version, keywords: version, company: version, qualifications: version, experience: version },
        changed_components: category ? [category] : ["settings"],
      };
      let draft: AnalysisContext = { ...seedContext, ...payload, id: `CTX-${version}`, status_label: "پیش‌نویس", attachments: [] };
      if (mode === "live") {
        const token = await csrf();
        const response = await fetch(`${API_BASE}/procurement/analysis-contexts/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify(payload) });
        if (!response.ok) throw new Error("ذخیره Snapshot پیش‌نویس انجام نشد.");
        draft = await response.json();
        if (category) {
          for (const file of files[category]) {
            const form = new FormData();
            form.append("context_snapshot", draft.id);
            form.append("category", category);
            form.append("file", file);
            const upload = await fetch(`${API_BASE}/procurement/analysis-context-files/`, { method: "POST", credentials: "include", headers: { "X-CSRFToken": token }, body: form });
            if (!upload.ok) throw new Error(`بارگذاری فایل ${file.name} انجام نشد.`);
          }
        }
      }
      setContexts((items) => [draft, ...items]);
      notify(`نسخه پیش‌نویس ${fa.format(version)} ذخیره شد و تنظیمات دوباره قفل شدند.`);
    } catch (error) { notify(error instanceof Error ? error.message : "ذخیره انجام نشد."); }
    finally { setBusy(false); }
  }

  async function saveSection(section: LockSection, category: FileCategory | null) { await createDraft(category); setLock(section, false); }
  async function activateContext(context: AnalysisContext) {
    if (!window.confirm(`نسخه ${context.version} فعال شود؟`)) return;
    if (mode === "live") {
      try { const token = await csrf(); const response = await fetch(`${API_BASE}/procurement/analysis-contexts/${context.id}/activate/`, { method: "POST", credentials: "include", headers: { "X-CSRFToken": token } }); if (!response.ok) throw new Error("فعال‌سازی انجام نشد."); } catch (error) { notify(error instanceof Error ? error.message : "فعال‌سازی انجام نشد."); return; }
    }
    setContexts((items) => items.map((item) => ({ ...item, status: item.id === context.id ? "active" : item.status === "active" ? "retired" : item.status, status_label: item.id === context.id ? "فعال" : item.status === "active" ? "بازنشسته" : item.status_label })));
    setEditor(contextEditor(context));
    notify("نسخه فعال شد؛ ChatGPT در اجرای بعدی تغییر را تشخیص می‌دهد.");
  }

  async function saveSchedule() {
    setBusy(true);
    try {
      if (mode === "live") {
        const token = await csrf();
        const response = await fetch(`${API_BASE}/procurement/automation-settings/${automation.id}/`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ enabled: automation.enabled, cadence: automation.cadence, interval_minutes: automation.interval_minutes, daily_time: automation.cadence === "daily" ? automation.daily_time : null, timezone_name: automation.timezone_name, analysis_delay_minutes: automation.analysis_delay_minutes, scheduled_task_enabled: automation.scheduled_task_enabled }) });
        if (!response.ok) throw new Error("ذخیره زمان‌بندی انجام نشد.");
        setAutomation(await response.json());
      }
      setLock("schedule", false);
      notify("زمان‌بندی ذخیره و دوباره قفل شد.");
    } catch (error) { notify(error instanceof Error ? error.message : "ذخیره انجام نشد."); }
    finally { setBusy(false); }
  }

  function recordActions(item: Notice) {
    if (noticeView === "all") return <>{!item.recommended && !item.stage && <button className={styles.primaryButton} onClick={() => recommendNotice(item)}>افزودن به پیشنهادی</button>}<button className={styles.secondaryButton} onClick={() => setSelected({ title: item.title, employer: item.employer, status: item.stage || (item.recommended ? "پیشنهادی" : "همه"), details: item.nextAction, deadline: item.deadline })}>مشاهده</button></>;
    if (noticeView === "recommended") return <><button className={styles.primaryButton} onClick={() => selectNotice(item)}>انتخاب</button><button className={styles.secondaryButton}>پیگیری</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { recommended: false })}>حذف</button></>;
    if (noticeView === "selected") return <><button className={styles.secondaryButton}>ثبت پیشرفت</button><button className={styles.primaryButton} onClick={() => submitNotice(item)}>ارسال شد</button><button className={styles.dangerButton} onClick={() => updateNotice(item.id, { stage: "", recommended: true, progress: 0 })}>حذف</button></>;
    if (noticeView === "submitted") return <><button className={styles.primaryButton} onClick={() => resultNotice(item)}>ثبت نتیجه</button><button className={styles.secondaryButton}>ثبت پیگیری</button></>;
    return <><button className={styles.secondaryButton}>اصلاح نتیجه</button><button className={styles.secondaryButton} onClick={() => notify(item.result === "برنده" ? "پیش‌نویس قرارداد به‌صورت خودکار ساخته خواهد شد." : "فقط نتیجه برنده وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button></>;
  }

  function directActions(item: DirectReferral) {
    if (directView === "all") return <><button className={styles.secondaryButton} onClick={() => setSelected({ title: item.title, employer: item.employer, status: directLabel(item.stage), details: item.nextAction, deadline: item.nextActionDue })}>مشاهده</button></>;
    if (directView === "recommended") return <><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "selected" })}>انتخاب</button><button className={styles.secondaryButton}>پیگیری</button><button className={styles.dangerButton} onClick={() => setDirect((items) => items.filter((current) => current.id !== item.id))}>حذف</button></>;
    if (directView === "selected") return <><button className={styles.secondaryButton} onClick={() => updateDirect(item.id, { stage: "preparing" })}>در دست تهیه</button><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "submitted" })}>ارسال شد</button><button className={styles.dangerButton}>حذف</button></>;
    if (directView === "submitted") return <><button className={styles.primaryButton} onClick={() => updateDirect(item.id, { stage: "won", nextAction: "ایجاد پیش‌نویس قرارداد" })}>ثبت موفق</button><button className={styles.secondaryButton}>ثبت پیگیری</button></>;
    return <button className={styles.secondaryButton} onClick={() => notify(item.stage === "won" ? "پیش‌نویس قرارداد به‌صورت خودکار ساخته خواهد شد." : "فقط نتیجه موفق وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button>;
  }

  function LockHeader({ section, title }: { section: LockSection; title: string }) {
    const open = editing[section];
    return <div className={styles.lockedHeader}><div><h2>{title}</h2><span className={`${styles.lockBadge} ${open ? styles.editBadge : ""}`}>{open ? "در حال ویرایش" : "ثبت‌شده و قفل"}</span></div>{!open && <button className={styles.secondaryButton} onClick={() => setLock(section, true)}>ویرایش</button>}</div>;
  }

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}><div><span>زیرسامانه تخصصی PDP One</span><h1>مناقصات و استعلامات</h1><p>مدیریت مناقصات، استعلامات و ارجاعات مستقیم همراه با تحلیل ChatGPT</p></div><Link href="/">بازگشت به سامانه</Link></header>
    <div className={styles.banner}><b>Preview تعاملی</b><span>{mode === "live" ? "رابط به Backend آزمایشی متصل است." : "داده‌ها نمونه‌اند و محیط واقعی تغییر نمی‌کند."}</span></div>
    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setSearch(""); setNoticeView("all"); setDirectView("all"); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article className={styles.kpi}><span>کل استخراج و ثبت</span><b>{fa.format(stats.reduce((sum, item) => sum + item.total, 0))}</b><small>سه مسیر فرصت</small></article>
        <article className={styles.kpi}><span>در حال شرکت یا پیگیری</span><b>{fa.format(activeTotal)}</b><small>منتخب و ارسال‌شده</small></article>
        <article className={styles.kpi}><span>برنده یا موفق</span><b>{fa.format(totalWon)}</b><small>آماده پیش‌نویس قرارداد</small></article>
        <article className={styles.kpi}><span>نرخ موفقیت</span><b>{fa.format(Math.round(totalWon / Math.max(activeTotal + totalWon, 1) * 100))}٪</b><small>نمونه فعلی</small></article>
        <article className={styles.kpi}><span>فوریت زیاد</span><b>{fa.format(urgentCount)}</b><small>نیازمند اقدام مدیریت</small></article>
        <article className={styles.kpi}><span>پیگیری عقب‌افتاده</span><b>۳</b><small>در همه مسیرها</small></article>
      </div>
      <div className={styles.chartGrid}>
        <article className={styles.panel}><h2>مقایسه آماری مسیرها</h2><div className={styles.legend}><span><i />کل استخراج/ثبت</span><span><i className={styles.activeLegend} />در حال شرکت/پیگیری</span><span><i className={styles.wonLegend} />برنده/موفق</span></div><div className={styles.barChart}>{stats.map((item) => <div className={styles.barGroup} key={item.label}><span>{item.label}</span><div className={styles.bars}><div className={`${styles.bar} ${styles.totalBar}`} style={{ height: `${Math.max(item.total / maxChart * 100, 8)}%` }}><b>{fa.format(item.total)}</b></div><div className={`${styles.bar} ${styles.activeBar}`} style={{ height: `${Math.max(item.active / maxChart * 100, 5)}%` }}><b>{fa.format(item.active)}</b></div><div className={`${styles.bar} ${styles.wonBar}`} style={{ height: `${Math.max(item.won / maxChart * 100, 3)}%` }}><b>{fa.format(item.won)}</b></div></div></div>)}</div></article>
        <article className={styles.panel}><h2>ترکیب پرونده‌های فعال</h2><div className={styles.donutWrap}><div className={styles.donut} style={{ background: donutBackground }}><div className={styles.donutCenter}><b>{fa.format(activeTotal)}</b><small>پرونده فعال</small></div></div><div className={styles.donutLegend}>{stats.map((item, index) => <div key={item.label}><span><i style={{ background: ["#2d7582", "#d5a52f", "#8d70a9"][index] }} />{item.label}</span><b>{fa.format(item.active)}</b></div>)}</div></div></article>
      </div>
      <div className={styles.miniGrid}>
        <article className={styles.panel}><h2>روند شش‌ماهه مشارکت</h2><div className={styles.trend}>{[["بهمن", 3], ["اسفند", 5], ["فروردین", 4], ["اردیبهشت", 7], ["خرداد", 9], ["تیر", 11]].map(([month, value]) => <div key={month}><b>{fa.format(Number(value))}</b><i style={{ height: `${Number(value) * 8}%` }} /><small>{month}</small></div>)}</div></article>
        <article className={styles.panel}><h2>هشدارها و پیشنهادهای آماری</h2><div className={styles.alertList}><span>نمایش نرخ تبدیل «پیشنهادی → منتخب → ارسال‌شده → برد» برای هر مسیر</span><span>مقایسه عملکرد منابع هزاره و پارس نماد</span><span>تفکیک فرصت‌ها بر اساس حوزه تخصصی، استان و کارفرما</span><span>مقایسه ماهانه و دوره مشابه سال قبل</span></div></article>
      </div>
      <article className={`${styles.panel} ${styles.activeCases}`}><div className={styles.sectionHeading}><div><span>انتهای داشبورد</span><h2>پرونده‌های فعال</h2></div><small>مناقصات، استعلامات و ارجاعات مستقیم منتخب یا ارسال‌شده</small></div><div className={styles.caseTable}>{activeCases.map((item) => { const u = urgency(item.deadline); return <button key={`${item.title}-${item.subtitle}`} onClick={() => setSelected({ title: item.title, employer: item.subtitle, status: item.stage, details: item.next, deadline: item.deadline })}><span><b>{item.title}</b><small>{item.subtitle}</small></span><span><b>{item.stage}</b><small>{item.next}</small></span><span className={`${styles.urgency} ${urgencyClass(u.tone)}`}><b>{u.label}</b><small>{u.remaining}</small></span></button>; })}</div></article>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section><div className={styles.sectionHeading}><div><span>فرآیند تصمیم‌گیری</span><h2>{tab === "tenders" ? "مناقصات" : "استعلامات"}</h2></div><small>در نمای «همه» می‌توانید رکورد را شخصاً به فهرست پیشنهادی اضافه کنید.</small></div><div className={styles.views}>{views.map(([id, label]) => <button key={id} className={noticeView === id ? styles.active : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div><div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی عنوان، کارفرما یا استان..." /><span>{fa.format(filteredNotices.length)} رکورد</span></div><div className={styles.recordList}>{filteredNotices.map((item) => { const u = urgency(item.deadline); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>{item.source} · {item.province}</small><span className={`${styles.urgency} ${urgencyClass(u.tone)}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{u.remaining}</span><span>اولویت: {item.score == null ? "تحلیل نشده" : `${fa.format(item.score)} از ۱۰۰`}</span><span>پیشرفت: {fa.format(item.progress)}٪</span></div></div><div className={styles.decision}><span className={styles.stage}>{item.result || (item.stage === "submitted" ? "ارسال‌شده" : item.stage ? "منتخب" : item.recommended ? "پیشنهادی" : "فقط در همه")}</span><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div></dl><div className={styles.actions}>{recordActions(item)}</div></div></article>; })}{!filteredNotices.length && <div className={styles.empty}>رکوردی در این نما وجود ندارد.</div>}</div></section>}

    {tab === "direct" && <section><div className={styles.sectionHeading}><div><span>فرآیند ارجاعات مستقیم</span><h2>ارجاعات مستقیم</h2></div><small>همان مسیر پیشنهادی، منتخب، ارسال‌شده و نتایج را دنبال می‌کند.</small></div><form className={styles.quickForm} onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); setDirect((items) => [{ id: `D-${Date.now()}`, title: String(form.get("title")), employer: String(form.get("employer")), province: "", type: "نیازمند تعیین", stage: "new", responsible: "ثبت‌کننده", nextAction: String(form.get("action")), nextActionDue: new Date(Date.now() + 86400000).toISOString(), probability: 20 }, ...items]); event.currentTarget.reset(); notify("ارجاع مستقیم در فهرست پیشنهادی ثبت شد."); }}><label>عنوان<input name="title" required /></label><label>کارفرما<input name="employer" required /></label><label>اقدام بعدی<input name="action" required /></label><button>ثبت در پیشنهادی</button></form><div className={styles.views}>{views.map(([id, label]) => <button key={id} className={directView === id ? styles.active : ""} onClick={() => setDirectView(id)}>{label}</button>)}</div><div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="جست‌وجوی ارجاع مستقیم..." /><span>{fa.format(filteredDirect.length)} رکورد</span></div><div className={styles.recordList}>{filteredDirect.map((item) => { const u = urgency(item.nextActionDue); return <article className={styles.record} key={item.id}><div><div className={styles.recordTop}><small>{item.type} · {item.province || "محل نامشخص"}</small><span className={`${styles.urgency} ${urgencyClass(u.tone)}`}>{u.label}</span></div><h3>{item.title}</h3><p>{item.employer}</p><div className={styles.facts}><span>{u.remaining}</span><span>احتمال تبدیل: {fa.format(item.probability)}٪</span></div></div><div className={styles.decision}><span className={styles.stage}>{directLabel(item.stage)}</span><dl><div><dt>مسئول</dt><dd>{item.responsible}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.nextAction}</dd></div></dl><div className={styles.actions}>{directActions(item)}</div></div></article>; })}</div></section>}

    {tab === "management" && <section><div className={styles.sectionHeading}><div><span>تنظیمات کنترل‌شده</span><h2>مدیریت زیرسامانه</h2></div><small>اطلاعات پس از ذخیره قفل می‌شوند و برای اصلاح باید صریحاً وارد حالت ویرایش شوید.</small></div><div className={styles.managementTabs}>{managementTabs.map(([id, label]) => <button key={id} className={managementView === id ? styles.active : ""} onClick={() => setManagementView(id)}>{label}</button>)}</div>
      {managementView === "extraction" && <div className={styles.managementGrid}><article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.sourceList}>{sources.map((source) => <div key={source.id}><label><input type="checkbox" checked={source.enabled} onChange={() => setSources((items) => items.map((item) => item.id === source.id ? { ...item, enabled: !item.enabled } : item))} /><b>{source.name}</b></label><span>{source.status_label}</span><small>{source.connectors.map((connector) => `${connector.notice_type_label}: ${connector.enabled ? "فعال" : "غیرفعال"}`).join(" · ")}</small></div>)}</div></article><article className={styles.panel}><h2>Connectorها و اجرای دستی</h2><div className={styles.connectorList}>{sources.flatMap((source) => source.connectors).map((connector) => <label key={connector.id}><input type="checkbox" defaultChecked={connector.enabled} disabled={!connector.enabled} /><span>{connector.key}</span><small>{connector.status_label}</small></label>)}</div><button className={styles.primaryButton} onClick={() => notify("استخراج Preview آغاز شد؛ محیط واقعی تغییر نمی‌کند.")}>شروع استخراج انتخاب‌شده</button></article><article className={`${styles.lockedCard} ${styles.activeCases}`}><LockHeader section="schedule" title="زمان‌بندی استخراج و تحلیل" /><div className={styles.scheduleGrid}><label>وضعیت خودکار<select disabled={!editing.schedule} value={automation.enabled ? "enabled" : "disabled"} onChange={(event) => setAutomation((current) => ({ ...current, enabled: event.target.value === "enabled" }))}><option value="disabled">غیرفعال</option><option value="enabled">فعال</option></select></label><label>نوع برنامه<select disabled={!editing.schedule} value={automation.cadence} onChange={(event) => setAutomation((current) => ({ ...current, cadence: event.target.value as "hourly" | "daily", cadence_label: event.target.value === "daily" ? "روزانه" : "ساعتی" }))}><option value="daily">روزانه</option><option value="hourly">ساعتی</option></select></label><label>فاصله ساعتی به دقیقه<input disabled={!editing.schedule || automation.cadence !== "hourly"} type="number" min="60" value={automation.interval_minutes} onChange={(event) => setAutomation((current) => ({ ...current, interval_minutes: Number(event.target.value) }))} /></label><label>ساعت روزانه<input disabled={!editing.schedule || automation.cadence !== "daily"} type="time" value={automation.daily_time || ""} onChange={(event) => setAutomation((current) => ({ ...current, daily_time: event.target.value }))} /></label><label>تأخیر تحلیل ChatGPT<input disabled={!editing.schedule} type="number" min="0" max="1440" value={automation.analysis_delay_minutes} onChange={(event) => setAutomation((current) => ({ ...current, analysis_delay_minutes: Number(event.target.value) }))} /></label><label>فرمان دستی<input disabled value={automation.manual_command} /></label></div>{editing.schedule && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setLock("schedule", false)}>انصراف</button><button className={styles.primaryButton} disabled={busy} onClick={saveSchedule}>ذخیره و قفل</button></div>}</article></div>}
      {managementView === "prompts" && <article className={styles.lockedCard}><LockHeader section="prompts" title="نقش و Prompt مشترک تحلیل" /><div className={styles.fields}><label className={styles.field}><span>نقش تخصصی ChatGPT</span><textarea rows={5} disabled={!editing.prompts} value={editor.role} onChange={(event) => setEditor((current) => ({ ...current, role: event.target.value }))} /></label><label className={styles.field}><span>دستورهای پایه</span><textarea rows={6} disabled={!editing.prompts} value={editor.base} onChange={(event) => setEditor((current) => ({ ...current, base: event.target.value }))} /></label><label className={styles.field}><span>Prompt مشترک مناقصات و استعلامات</span><textarea rows={8} disabled={!editing.prompts} value={editor.prompt} onChange={(event) => setEditor((current) => ({ ...current, prompt: event.target.value }))} /><small>همین Prompt برای هر دو نوع فراخوان استفاده می‌شود و تشخیص تفاوت‌ها بر اساس نوع رکورد انجام می‌شود.</small></label><div className={styles.fileBox}><b>بارگذاری فایل مرجع Prompt</b><input type="file" disabled={!editing.prompts} accept=".txt,.md,.pdf,.doc,.docx" multiple onChange={(event) => handleFiles("prompt_reference", event)} /><div className={styles.fileList}>{files.prompt_reference.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}</div></div></div>{editing.prompts && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setLock("prompts", false)}>انصراف</button><button className={styles.primaryButton} disabled={busy} onClick={() => saveSection("prompts", "prompt_reference")}>ذخیره پیش‌نویس و قفل</button></div>}</article>}
      {managementView === "keywords" && <article className={styles.lockedCard}><LockHeader section="keywords" title="کلیدواژه‌های تحلیل" /><div className={styles.fields}><label className={styles.field}><span>کلیدواژه‌های فعال</span><textarea rows={12} disabled={!editing.keywords} value={editor.activeKeywords} onChange={(event) => setEditor((current) => ({ ...current, activeKeywords: event.target.value }))} /><small>هر کلیدواژه در یک خط؛ کلیدواژه به‌تنهایی تصمیم قطعی ایجاد نمی‌کند.</small></label><label className={styles.field}><span>کلیدواژه‌های حذف یا احتیاط</span><textarea rows={7} disabled={!editing.keywords} value={editor.excludedKeywords} onChange={(event) => setEditor((current) => ({ ...current, excludedKeywords: event.target.value }))} /></label><div className={styles.fileBox}><b>بارگذاری فایل کلیدواژه</b><input type="file" disabled={!editing.keywords} accept=".txt,.md,.pdf,.doc,.docx" multiple onChange={(event) => handleFiles("keywords", event)} /><small>فایل TXT یا MD در Preview مستقیماً داخل فهرست خوانده می‌شود؛ سایر فایل‌ها به Snapshot پیش‌نویس پیوست می‌شوند.</small><div className={styles.fileList}>{files.keywords.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}</div></div></div>{editing.keywords && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setLock("keywords", false)}>انصراف</button><button className={styles.primaryButton} disabled={busy} onClick={() => saveSection("keywords", "keywords")}>ذخیره پیش‌نویس و قفل</button></div>}</article>}
      {managementView === "company" && <article className={styles.lockedCard}><LockHeader section="company" title="پروفایل، صلاحیت‌ها و رزومه شرکت" /><div className={styles.fields}><label className={styles.field}><span>پروفایل خلاصه شرکت</span><textarea rows={7} disabled={!editing.company} value={editor.companyProfile} onChange={(event) => setEditor((current) => ({ ...current, companyProfile: event.target.value }))} /></label><label className={styles.field}><span>صلاحیت‌ها و رتبه‌ها</span><textarea rows={9} disabled={!editing.company} value={editor.qualifications} onChange={(event) => setEditor((current) => ({ ...current, qualifications: event.target.value }))} /></label><label className={styles.field}><span>خلاصه سوابق و تجربیات</span><textarea rows={10} disabled={!editing.company} value={editor.experience} onChange={(event) => setEditor((current) => ({ ...current, experience: event.target.value }))} /></label><div className={styles.fileBox}><b>بارگذاری پروفایل، صلاحیت یا رزومه</b><input type="file" disabled={!editing.company} accept=".txt,.md,.pdf,.doc,.docx" multiple onChange={(event) => handleFiles("resume", event)} /><small>رزومه PDF یا Word در فضای خصوصی نگهداری و به Snapshot مرتبط می‌شود.</small><div className={styles.fileList}>{files.resume.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}</div></div></div>{editing.company && <div className={styles.editorActions}><button className={styles.secondaryButton} onClick={() => setLock("company", false)}>انصراف</button><button className={styles.primaryButton} disabled={busy} onClick={() => saveSection("company", "resume")}>ذخیره پیش‌نویس و قفل</button></div>}</article>}
      {managementView === "versions" && <div className={styles.managementGrid}><article className={styles.panel}><h2>نسخه فعال</h2><dl><div><dt>نسخه</dt><dd>{fa.format(activeContext.version)}</dd></div><div><dt>وضعیت</dt><dd>{activeContext.status_label}</dd></div><div><dt>Prompt</dt><dd>مشترک مناقصات و استعلامات</dd></div><div><dt>فرمان دستی</dt><dd>PDP</dd></div></dl></article><article className={styles.panel}><h2>پیش‌نویس‌های آماده بررسی</h2><div className={styles.versionList}>{draftContexts.map((context) => <div className={styles.versionItem} key={context.id}><span><b>نسخه {fa.format(context.version)}</b><small>{context.attachments?.length || 0} فایل پیوست</small></span><button className={styles.primaryButton} onClick={() => activateContext(context)}>فعال‌سازی</button></div>)}{!draftContexts.length && <p>پیش‌نویس جدیدی وجود ندارد.</p>}</div></article></div>}
    </section>}

    {selected && <div className={styles.backdrop} onMouseDown={() => setSelected(null)}><section className={styles.modal} onMouseDown={(event) => event.stopPropagation()}><header className={styles.modalHeader}><div><small>{selected.status}</small><h2>{selected.title}</h2><p>{selected.employer}</p></div><button onClick={() => setSelected(null)}>×</button></header><div className={styles.modalBody}><div className={styles.detailGrid}><article><h3>وضعیت و زمان</h3><dl><div><dt>وضعیت</dt><dd>{selected.status}</dd></div><div><dt>مهلت</dt><dd>{selected.deadline ? faDate.format(new Date(selected.deadline)) : "تعیین نشده"}</dd></div><div><dt>زمان باقی‌مانده</dt><dd>{urgency(selected.deadline).remaining}</dd></div></dl></article><article><h3>اقدام بعدی</h3><p>{selected.details}</p></article></div></div></section></div>}
  </main>;
}
