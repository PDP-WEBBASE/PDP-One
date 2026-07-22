"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./workspace.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type WorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";
type ManagementView = "extraction" | "prompts" | "keywords" | "company" | "versions";
type DetailTab = "summary" | "followup" | "documents" | "more";
type DataMode = "loading" | "live" | "demo";
type UrgencyTone = "critical" | "high" | "medium" | "normal" | "unknown";

type Notice = {
  id: string;
  kind: "tender" | "inquiry";
  title: string;
  employer_name: string;
  province: string;
  source_label: string;
  published_at: string | null;
  deadline: string | null;
  status_label: string;
  recommended: boolean;
  stage: "" | "selected" | "preparing" | "submitted" | "results";
  stage_label: string;
  result_label: string;
  score: number | null;
  responsible: string;
  next_action: string;
  next_action_due: string | null;
  progress: number;
  recommendation_reason: string;
  risk_notes: string;
  documents: string[];
  missing_information: string[];
  description: string;
  estimated_amount: string;
  guarantee: string;
};

type DirectStage =
  | "new"
  | "reviewing"
  | "following_up"
  | "negotiating"
  | "selected"
  | "preparing"
  | "submitted"
  | "won"
  | "lost"
  | "stopped"
  | "deferred"
  | "converted_to_notice"
  | "converted_to_contract";

type DirectOpportunity = {
  id: string;
  title: string;
  employer_name: string;
  opportunity_type: string;
  opportunity_type_label: string;
  stage: DirectStage;
  stage_label: string;
  responsible_username: string;
  next_action: string;
  next_action_due: string | null;
  probability_percent: number | null;
  province: string;
  description: string;
  documents: string[];
  result_label: string;
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

type AutomationSettings = {
  id: string;
  enabled: boolean;
  cadence_label: string;
  daily_time: string | null;
  analysis_delay_minutes: number;
  manual_command: string;
};

type AnalysisContext = {
  id: string;
  version: number;
  status: "draft" | "active" | "retired";
  status_label: string;
  role_text: string;
  base_instructions: string;
  tender_prompt: string;
  inquiry_prompt: string;
  company_profile: Record<string, unknown>;
  qualifications: unknown[];
  keywords: Record<string, unknown>;
  experience_summary: unknown[];
  component_versions: Record<string, number>;
  changed_components: string[];
  activated_at?: string | null;
};

type ContextEditor = {
  roleText: string;
  baseInstructions: string;
  tenderPrompt: string;
  inquiryPrompt: string;
  activeKeywords: string;
  excludedKeywords: string;
  companyProfile: string;
  qualifications: string;
  experienceSummary: string;
};

type SelectedDetail =
  | { type: "notice"; item: Notice }
  | { type: "direct"; item: DirectOpportunity }
  | null;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const faNumber = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "short", day: "numeric" });
const faDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

const seedNotices: Notice[] = [
  {
    id: "T-001", kind: "tender", title: "خدمات مشاوره طراحی و نظارت مجموعه اداری", employer_name: "شرکت توسعه عمران", province: "تهران", source_label: "هزاره", published_at: "2026-07-21T08:00:00+03:30", deadline: "2026-07-25T16:00:00+03:30", status_label: "تحلیل‌شده", recommended: true, stage: "selected", stage_label: "منتخب", result_label: "", score: 91, responsible: "محمد ملکی", next_action: "تقسیم کار تهیه پیشنهاد", next_action_due: "2026-07-23T10:00:00+03:30", progress: 35, recommendation_reason: "انطباق مستقیم با رتبه معماری و سابقه طراحی و نظارت شرکت.", risk_notes: "زمان تهیه پیشنهاد محدود است.", documents: ["آگهی اصلی", "شرایط شرکت"], missing_information: ["مبلغ برآورد در منبع درج نشده است"], description: "طراحی مراحل یک و دو و نظارت بر اجرای مجموعه اداری.", estimated_amount: "در اسناد اعلام می‌شود", guarantee: "نیازمند بررسی"
  },
  {
    id: "T-002", kind: "tender", title: "مطالعات طرح جامع و برنامه‌ریزی فضایی", employer_name: "اداره کل راه و شهرسازی", province: "فارس", source_label: "پارس نماد داده", published_at: "2026-07-20T09:30:00+03:30", deadline: "2026-07-30T14:00:00+03:30", status_label: "تحلیل‌شده", recommended: true, stage: "preparing", stage_label: "منتخب", result_label: "", score: 95, responsible: "کارشناس مناقصات", next_action: "تهیه ساختار شکست خدمات", next_action_due: "2026-07-24T11:00:00+03:30", progress: 62, recommendation_reason: "هم‌راستا با رتبه مطالعات جغرافیایی و برنامه‌ریزی فضایی شرکت.", risk_notes: "نیاز به تیم چندتخصصی دارد.", documents: ["آگهی اصلی", "شرح خدمات"], missing_information: [], description: "شناخت، تحلیل وضع موجود، سناریوسازی و ارائه برنامه اجرایی.", estimated_amount: "۴۵ میلیارد ریال", guarantee: "۲ میلیارد ریال"
  },
  {
    id: "T-003", kind: "tender", title: "طراحی تأسیسات مکانیکی و برقی بیمارستان", employer_name: "دانشگاه علوم پزشکی", province: "البرز", source_label: "هزاره", published_at: "2026-07-22T07:20:00+03:30", deadline: "2026-07-27T12:00:00+03:30", status_label: "در انتظار تحلیل", recommended: false, stage: "", stage_label: "", result_label: "", score: null, responsible: "", next_action: "دریافت جزئیات و اجرای تحلیل", next_action_due: null, progress: 0, recommendation_reason: "تحلیل ChatGPT هنوز انجام نشده است.", risk_notes: "اطلاعات جزئیات ناقص است.", documents: ["آگهی اصلی"], missing_information: ["صفحه جزئیات منبع دریافت نشده است"], description: "طراحی تأسیسات یک بیمارستان جدید.", estimated_amount: "نامشخص", guarantee: "نامشخص"
  },
  {
    id: "T-004", kind: "tender", title: "مطالعات امکان‌سنجی شهرک صنعتی", employer_name: "شرکت شهرک‌های صنعتی", province: "آذربایجان شرقی", source_label: "پارس نماد داده", published_at: "2026-07-15T09:00:00+03:30", deadline: "2026-07-22T15:00:00+03:30", status_label: "ارسال‌شده", recommended: true, stage: "submitted", stage_label: "ارسال‌شده", result_label: "", score: 82, responsible: "توسعه کسب‌وکار", next_action: "پیگیری نتیجه اولیه", next_action_due: "2026-07-26T09:00:00+03:30", progress: 100, recommendation_reason: "تناسب با پروانه فنی و مهندسی صنعت و معدن.", risk_notes: "رقابت زیاد و حساسیت مالی.", documents: ["آگهی اصلی", "پیشنهاد فنی", "پیشنهاد مالی", "رسید ارسال"], missing_information: [], description: "امکان‌سنجی فنی، اقتصادی و مکانی شهرک صنعتی.", estimated_amount: "۳۸ میلیارد ریال", guarantee: "۱.۵ میلیارد ریال"
  },
  {
    id: "T-005", kind: "tender", title: "خدمات طراحی معماری مجتمع آموزشی", employer_name: "سازمان نوسازی مدارس", province: "قم", source_label: "هزاره", published_at: "2026-06-30T08:00:00+03:30", deadline: "2026-07-10T12:00:00+03:30", status_label: "نتیجه ثبت‌شده", recommended: true, stage: "results", stage_label: "نتایج", result_label: "برنده", score: 94, responsible: "مدیرعامل", next_action: "آماده‌سازی پیش‌نویس قرارداد", next_action_due: "2026-07-24T10:00:00+03:30", progress: 100, recommendation_reason: "سابقه و رتبه مستقیم در پروژه‌های آموزشی.", risk_notes: "کنترل برنامه زمانی قرارداد.", documents: ["آگهی اصلی", "پیشنهاد فنی", "اعلام برنده"], missing_information: [], description: "طراحی معماری مجتمع آموزشی و محوطه وابسته.", estimated_amount: "۶۲ میلیارد ریال", guarantee: "۳ میلیارد ریال"
  },
  {
    id: "I-001", kind: "inquiry", title: "استعلام خدمات نقشه‌برداری و برداشت وضع موجود", employer_name: "شهرداری منطقه", province: "تهران", source_label: "پارس نماد داده", published_at: "2026-07-22T09:00:00+03:30", deadline: "2026-07-23T13:00:00+03:30", status_label: "تحلیل‌شده", recommended: true, stage: "selected", stage_label: "منتخب", result_label: "", score: 88, responsible: "کارشناس مناقصات", next_action: "دریافت قیمت و تأیید مدیر", next_action_due: "2026-07-23T09:00:00+03:30", progress: 70, recommendation_reason: "قابل پاسخ سریع و مرتبط با خدمات پایه مشاوره.", risk_notes: "کمتر از ۲۴ ساعت زمان باقی مانده است.", documents: ["استعلام", "شرح مختصر خدمات"], missing_information: [], description: "برداشت وضع موجود و تهیه نقشه پایه.", estimated_amount: "نیازمند اعلام قیمت", guarantee: "ندارد"
  },
  {
    id: "I-002", kind: "inquiry", title: "استعلام تهیه گزارش توجیهی و امکان‌سنجی", employer_name: "منطقه ویژه اقتصادی", province: "بوشهر", source_label: "هزاره", published_at: "2026-07-21T11:00:00+03:30", deadline: "2026-07-26T15:00:00+03:30", status_label: "تحلیل‌شده", recommended: true, stage: "preparing", stage_label: "منتخب", result_label: "", score: 86, responsible: "واحد مطالعات", next_action: "جلسه با کارشناس مالی", next_action_due: "2026-07-24T09:30:00+03:30", progress: 48, recommendation_reason: "مرتبط با مطالعات امکان‌سنجی و ارزیابی سرمایه‌گذاری.", risk_notes: "نیازمند ورودی مالی است.", documents: ["استعلام", "شرح خدمات"], missing_information: [], description: "گزارش توجیهی فنی و اقتصادی طرح سرمایه‌گذاری.", estimated_amount: "در حال برآورد", guarantee: "ندارد"
  },
  {
    id: "I-003", kind: "inquiry", title: "استعلام طراحی روشنایی محوطه صنعتی", employer_name: "شرکت تولیدی نمونه", province: "قزوین", source_label: "پارس نماد داده", published_at: "2026-07-22T10:10:00+03:30", deadline: "2026-07-24T10:00:00+03:30", status_label: "در انتظار تحلیل", recommended: false, stage: "", stage_label: "", result_label: "", score: null, responsible: "", next_action: "دریافت پیوست فنی", next_action_due: null, progress: 0, recommendation_reason: "هنوز تحلیل نشده است.", risk_notes: "جزئیات فنی ناقص است.", documents: ["استعلام"], missing_information: ["توان و محدوده روشنایی مشخص نیست"], description: "طراحی روشنایی محوطه صنعتی.", estimated_amount: "نامشخص", guarantee: "ندارد"
  },
  {
    id: "I-004", kind: "inquiry", title: "استعلام بازنگری نقشه‌های معماری", employer_name: "شرکت عمران و مسکن", province: "مازندران", source_label: "هزاره", published_at: "2026-07-10T09:00:00+03:30", deadline: "2026-07-18T12:00:00+03:30", status_label: "نتیجه ثبت‌شده", recommended: true, stage: "results", stage_label: "نتایج", result_label: "ناموفق", score: 79, responsible: "واحد فنی", next_action: "جلسه مرور نتیجه", next_action_due: "2026-07-25T10:00:00+03:30", progress: 100, recommendation_reason: "مرتبط با خدمات معماری و قابل انجام در زمان کوتاه.", risk_notes: "رقابت قیمتی زیاد بود.", documents: ["استعلام", "پیشنهاد قیمت", "ایمیل ارسال", "اعلام نتیجه"], missing_information: [], description: "بازنگری محدود نقشه‌های معماری.", estimated_amount: "۴.۸ میلیارد ریال", guarantee: "ندارد"
  }
];

const seedDirect: DirectOpportunity[] = [
  { id: "D-001", title: "رایزنی طرح توسعه پردیس اداری", employer_name: "گروه سرمایه‌گذاری پارس", opportunity_type: "employer_outreach", opportunity_type_label: "رایزنی با کارفرما", stage: "reviewing", stage_label: "در حال بررسی", responsible_username: "محمد ملکی", next_action: "ارسال معرفی‌نامه سوابق", next_action_due: "2026-07-23T11:00:00+03:30", probability_percent: 70, province: "تهران", description: "فرصت مستقیم برای طراحی و مدیریت طرح توسعه پردیس اداری.", documents: ["یادداشت جلسه اولیه"], result_label: "" },
  { id: "D-002", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer_name: "شرکت انرژی نو", opportunity_type: "direct_referral", opportunity_type_label: "معرفی مستقیم", stage: "selected", stage_label: "منتخب", responsible_username: "توسعه کسب‌وکار", next_action: "هماهنگی جلسه فنی", next_action_due: "2026-07-25T10:00:00+03:30", probability_percent: 55, province: "یزد", description: "بررسی امکان‌سنجی فنی و اقتصادی نیروگاه خورشیدی.", documents: [], result_label: "" },
  { id: "D-003", title: "دعوت محدود طراحی مجموعه درمانی", employer_name: "بنیاد توسعه سلامت", opportunity_type: "limited_invitation", opportunity_type_label: "دعوت محدود", stage: "submitted", stage_label: "پیشنهاد ارسال‌شده", responsible_username: "مدیر فنی", next_action: "پیگیری دریافت پیشنهاد", next_action_due: "2026-07-24T09:00:00+03:30", probability_percent: 80, province: "تهران", description: "دعوت مستقیم برای طراحی معماری و تأسیسات مجموعه درمانی.", documents: ["دعوت‌نامه", "پیشنهاد اولیه"], result_label: "" },
  { id: "D-004", title: "طراحی مرکز خدمات شهری", employer_name: "شرکت عمران شهری", opportunity_type: "direct_negotiation", opportunity_type_label: "مذاکره مستقیم", stage: "won", stage_label: "موفق", responsible_username: "مدیرعامل", next_action: "آماده‌سازی پیش‌نویس قرارداد", next_action_due: "2026-07-26T10:00:00+03:30", probability_percent: 100, province: "البرز", description: "فرصت مستقیم به نتیجه موفق رسیده است.", documents: ["صورتجلسه مذاکره", "اعلام موافقت"], result_label: "موفق" }
];

const seedSources: Source[] = [
  { id: "S-H", name: "هزاره", enabled: true, status_label: "فعال", connectors: [
    { id: "C-HT", key: "hezareh_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده اجرا" },
    { id: "C-HI", key: "hezareh_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده اجرا" }
  ] },
  { id: "S-P", name: "پارس نماد داده", enabled: true, status_label: "فعال", connectors: [
    { id: "C-PT", key: "parsnamad_tenders", notice_type_label: "مناقصات", enabled: true, status_label: "آماده اجرا" },
    { id: "C-PI", key: "parsnamad_inquiries", notice_type_label: "استعلامات", enabled: true, status_label: "آماده اجرا" }
  ] },
  { id: "S-S", name: "ستاد ایران", enabled: false, status_label: "موقتاً تعلیق‌شده / نیازمند بررسی مجدد در ساعت دسترسی", connectors: [
    { id: "C-ST", key: "setad_tenders", notice_type_label: "مناقصات", enabled: false, status_label: "نیازمند بررسی" },
    { id: "C-SI", key: "setad_inquiries", notice_type_label: "استعلامات", enabled: false, status_label: "نیازمند بررسی" }
  ] }
];

const seedAutomation: AutomationSettings = { id: "A-001", enabled: false, cadence_label: "روزانه", daily_time: "17:00", analysis_delay_minutes: 60, manual_command: "PDP" };

const seedContext: AnalysisContext = {
  id: "CTX-12",
  version: 12,
  status: "active",
  status_label: "فعال",
  role_text: "تحلیلگر ارشد مناقصات، استعلامات و فرصت‌های کسب‌وکار شرکت مهندسین مشاور طرح و برنامه پارس",
  base_instructions: "تحلیل باید بر مبنای تناسب واقعی با صلاحیت‌ها، ظرفیت اجرایی، زمان، ریسک و سوابق شرکت انجام شود. نتیجه فقط پیش‌نویس است و تصمیم نهایی انسانی باقی می‌ماند.",
  tender_prompt: "مناقصه را از نظر صلاحیت، حوزه تخصصی، زمان باقی‌مانده، تضمین، اسناد، ریسک و امکان تهیه پیشنهاد ارزیابی کن.",
  inquiry_prompt: "استعلام را با تأکید بر فوریت پاسخ، امکان قیمت‌گذاری سریع، اطلاعات تماس، اسناد لازم و ظرفیت پاسخ امروز ارزیابی کن.",
  company_profile: { summary: "شرکت مهندسین مشاور طرح و برنامه پارس؛ فعال در معماری، شهرسازی، تأسیسات، برنامه‌ریزی فضایی و مطالعات امکان‌سنجی." },
  qualifications: ["رتبه ۳ معماری", "رتبه ۳ شهرسازی", "رتبه ۳ تأسیسات برق و مکانیک", "مطالعات جغرافیایی و برنامه‌ریزی فضایی", "پروانه فنی و مهندسی صنعت و معدن"],
  keywords: { active: ["طراحی معماری", "نظارت", "طرح جامع", "امکان‌سنجی", "تأسیسات"], excluded: ["تأمین کالا", "اجرای صرف", "خرید تجهیزات"] },
  experience_summary: ["پروژه‌های اداری و آموزشی", "مطالعات شهری و منطقه‌ای", "طراحی تأسیسات", "مطالعات توجیهی و امکان‌سنجی"],
  component_versions: { role: 3, prompts: 5, keywords: 8, company_profile: 3, qualifications: 4, experience: 7 },
  changed_components: [],
  activated_at: "2026-07-22T08:00:00+03:30"
};

function listOf<T>(payload: T[] | { results?: T[] }): T[] {
  return Array.isArray(payload) ? payload : payload.results || [];
}

function safeDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value.length === 10 ? `${value}T23:59:59` : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function displayDate(value: string | null) {
  const date = safeDate(value);
  return date ? faDate.format(date) : "تعیین نشده";
}

function displayDateTime(value: string | null) {
  const date = safeDate(value);
  return date ? faDateTime.format(date) : "تعیین نشده";
}

function urgency(value: string | null): { tone: UrgencyTone; label: string; remaining: string } {
  const date = safeDate(value);
  if (!date) return { tone: "unknown", label: "تاریخ نامشخص", remaining: "زمان نامشخص" };
  const hours = Math.ceil((date.getTime() - Date.now()) / 3600000);
  if (hours < 0) return { tone: "critical", label: "مهلت گذشته", remaining: `${faNumber.format(Math.abs(hours))} ساعت گذشته` };
  if (hours < 24) return { tone: "critical", label: "فوریت بحرانی", remaining: `${faNumber.format(hours)} ساعت باقی‌مانده` };
  if (hours <= 72) return { tone: "high", label: "فوریت زیاد", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  if (hours <= 168) return { tone: "medium", label: "فوریت متوسط", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
  return { tone: "normal", label: "فوریت عادی", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده` };
}

function splitLines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function jsonString(value: unknown, fallback = "") {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(String).join("\n");
  if (value && typeof value === "object") {
    const summary = (value as Record<string, unknown>).summary;
    if (typeof summary === "string") return summary;
  }
  return fallback;
}

function keywordLines(value: Record<string, unknown>, key: string) {
  const items = value[key];
  return Array.isArray(items) ? items.map(String).join("\n") : "";
}

function contextToEditor(context: AnalysisContext): ContextEditor {
  return {
    roleText: context.role_text,
    baseInstructions: context.base_instructions,
    tenderPrompt: context.tender_prompt,
    inquiryPrompt: context.inquiry_prompt,
    activeKeywords: keywordLines(context.keywords, "active"),
    excludedKeywords: keywordLines(context.keywords, "excluded"),
    companyProfile: jsonString(context.company_profile),
    qualifications: jsonString(context.qualifications),
    experienceSummary: jsonString(context.experience_summary),
  };
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include" });
  if (!response.ok) throw new Error("دریافت نشست کاربر انجام نشد.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function noticeMatches(item: Notice, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return item.recommended && !item.stage;
  if (view === "selected") return item.stage === "selected" || item.stage === "preparing";
  if (view === "submitted") return item.stage === "submitted";
  return item.stage === "results";
}

const directRecommendedStages: DirectStage[] = ["new", "reviewing", "following_up", "negotiating"];
const directSelectedStages: DirectStage[] = ["selected", "preparing"];
const directResultStages: DirectStage[] = ["won", "lost", "stopped", "deferred", "converted_to_notice", "converted_to_contract"];

function directMatches(item: DirectOpportunity, view: WorkflowView) {
  if (view === "all") return true;
  if (view === "recommended") return directRecommendedStages.includes(item.stage);
  if (view === "selected") return directSelectedStages.includes(item.stage);
  if (view === "submitted") return item.stage === "submitted";
  return directResultStages.includes(item.stage);
}

export default function ProcurementWorkspace() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<WorkflowView>("all");
  const [directView, setDirectView] = useState<WorkflowView>("all");
  const [managementView, setManagementView] = useState<ManagementView>("extraction");
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");
  const [selectedDetail, setSelectedDetail] = useState<SelectedDetail>(null);
  const [mode, setMode] = useState<DataMode>("loading");
  const [notices, setNotices] = useState<Notice[]>(seedNotices);
  const [direct, setDirect] = useState<DirectOpportunity[]>(seedDirect);
  const [sources, setSources] = useState<Source[]>(seedSources);
  const [automation, setAutomation] = useState<AutomationSettings>(seedAutomation);
  const [contexts, setContexts] = useState<AnalysisContext[]>([seedContext]);
  const [editor, setEditor] = useState<ContextEditor>(contextToEditor(seedContext));
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>(["C-HT", "C-HI", "C-PT", "C-PI"]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const responses = await Promise.all([
          fetch(`${API_BASE}/procurement/tenders/?ordering=-last_seen_at`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/inquiries/?ordering=-last_seen_at`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/direct-opportunities/?ordering=next_action_due`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/sources/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/automation-settings/`, { credentials: "include" }),
          fetch(`${API_BASE}/procurement/analysis-contexts/`, { credentials: "include" }),
        ]);
        if (responses.some((response) => !response.ok)) throw new Error("preview-backend-unavailable");
        const [tendersData, inquiriesData, directData, sourceData, automationData, contextData] = await Promise.all(responses.map((response) => response.json()));
        if (cancelled) return;
        const liveNotices: Notice[] = [
          ...listOf<Record<string, unknown>>(tendersData).map((item) => ({
            id: String(item.id), kind: "tender" as const, title: String(item.title || ""), employer_name: String(item.employer_name || ""), province: String(item.province || ""), source_label: `${faNumber.format(Number(item.source_count || 1))} منبع`, published_at: item.published_date ? String(item.published_date) : null, deadline: item.submission_deadline ? String(item.submission_deadline) : null, status_label: String(item.processing_status_label || ""), recommended: Boolean(item.is_recommended), stage: item.case_stage === "submitted" ? "submitted" : item.case_stage === "selected" ? "selected" : item.case_stage ? "preparing" : "", stage_label: String(item.case_stage_label || ""), result_label: "", score: null, responsible: "", next_action: "", next_action_due: null, progress: 0, recommendation_reason: "برای مشاهده تحلیل کامل، جزئیات فراخوان را باز کنید.", risk_notes: "", documents: [], missing_information: [], description: "", estimated_amount: "نامشخص", guarantee: "نامشخص"
          })),
          ...listOf<Record<string, unknown>>(inquiriesData).map((item) => ({
            id: String(item.id), kind: "inquiry" as const, title: String(item.title || ""), employer_name: String(item.employer_name || ""), province: String(item.province || ""), source_label: `${faNumber.format(Number(item.source_count || 1))} منبع`, published_at: item.published_date ? String(item.published_date) : null, deadline: item.submission_deadline ? String(item.submission_deadline) : null, status_label: String(item.processing_status_label || ""), recommended: Boolean(item.is_recommended), stage: item.case_stage === "submitted" ? "submitted" : item.case_stage === "selected" ? "selected" : item.case_stage ? "preparing" : "", stage_label: String(item.case_stage_label || ""), result_label: "", score: null, responsible: "", next_action: "", next_action_due: null, progress: 0, recommendation_reason: "برای مشاهده تحلیل کامل، جزئیات فراخوان را باز کنید.", risk_notes: "", documents: [], missing_information: [], description: "", estimated_amount: "نامشخص", guarantee: "نامشخص"
          })),
        ];
        const liveDirect = listOf<Record<string, unknown>>(directData).map((item) => ({
          id: String(item.id), title: String(item.title || ""), employer_name: String(item.employer_name || ""), opportunity_type: String(item.opportunity_type || "unassigned"), opportunity_type_label: String(item.opportunity_type_label || "نیازمند تعیین"), stage: String(item.stage || "new") as DirectStage, stage_label: String(item.stage_label || "فرصت جدید"), responsible_username: String(item.responsible_username || ""), next_action: String(item.next_action || ""), next_action_due: item.next_action_due ? String(item.next_action_due) : null, probability_percent: item.probability_percent == null ? null : Number(item.probability_percent), province: String(item.province || ""), description: "", documents: [], result_label: ""
        }));
        const liveContexts = listOf<AnalysisContext>(contextData);
        setNotices(liveNotices);
        setDirect(liveDirect);
        setSources(listOf<Source>(sourceData));
        setAutomation(listOf<AutomationSettings>(automationData)[0] || seedAutomation);
        setContexts(liveContexts.length ? liveContexts : [seedContext]);
        const active = liveContexts.find((item) => item.status === "active") || liveContexts[0] || seedContext;
        setEditor(contextToEditor(active));
        setSelectedConnectors(listOf<Source>(sourceData).flatMap((source) => source.connectors.filter((connector) => source.enabled && connector.enabled).map((connector) => connector.id)));
        setMode("live");
      } catch {
        if (!cancelled) setMode("demo");
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const activeContext = useMemo(() => contexts.find((item) => item.status === "active") || contexts[0] || seedContext, [contexts]);
  const draftContexts = useMemo(() => contexts.filter((item) => item.status === "draft"), [contexts]);
  const maxContextVersion = useMemo(() => Math.max(...contexts.map((item) => item.version), 0), [contexts]);
  const visibleNotices = useMemo(() => notices.filter((item) => {
    const matchesTab = tab === "tenders" ? item.kind === "tender" : item.kind === "inquiry";
    const text = `${item.title} ${item.employer_name} ${item.province} ${item.source_label}`;
    return matchesTab && noticeMatches(item, noticeView) && (!search || text.includes(search));
  }), [noticeView, notices, search, tab]);
  const visibleDirect = useMemo(() => direct.filter((item) => directMatches(item, directView) && (!search || `${item.title} ${item.employer_name} ${item.province}`.includes(search))), [direct, directView, search]);
  const activeCases = useMemo(() => notices.filter((item) => ["selected", "preparing", "submitted"].includes(item.stage)), [notices]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 4200);
  }

  function updateEditor(field: keyof ContextEditor, value: string) {
    setEditor((current) => ({ ...current, [field]: value }));
  }

  function updateNotice(id: string, updater: (item: Notice) => Notice) {
    setNotices((items) => items.map((item) => item.id === id ? updater(item) : item));
  }

  function openDetail(detail: SelectedDetail) {
    setSelectedDetail(detail);
    setDetailTab("summary");
  }

  function selectNotice(item: Notice) {
    updateNotice(item.id, (current) => ({ ...current, stage: "selected", stage_label: "منتخب", responsible: current.responsible || "محمد ملکی", next_action: "تعیین برنامه تهیه پیشنهاد", next_action_due: new Date(Date.now() + 86400000).toISOString(), progress: 5 }));
    notify("رکورد به فهرست منتخب منتقل شد.");
  }

  function removeNoticeFromCurrent(item: Notice, fromSelected: boolean) {
    const reason = window.prompt("دلیل حذف را ثبت کنید:", "تصمیم مدیریت");
    if (!reason) return;
    if (fromSelected) {
      const returnToRecommended = window.confirm("برای بازگشت به پیشنهادی «تأیید» را بزنید؛ برای خروج از فرایند «لغو» را انتخاب کنید.");
      updateNotice(item.id, (current) => ({ ...current, recommended: returnToRecommended, stage: "", stage_label: "", progress: 0, status_label: `${returnToRecommended ? "بازگشت به پیشنهادی" : "خروج از فرایند"}: ${reason}` }));
    } else {
      updateNotice(item.id, (current) => ({ ...current, recommended: false, status_label: `حذف از پیشنهادها: ${reason}` }));
    }
    notify("رکورد از فهرست جاری خارج شد؛ سابقه باقی مانده است.");
  }

  function markNoticeSubmitted(item: Notice) {
    const tracking = window.prompt("شماره رهگیری یا رسید ارسال را وارد کنید:", "PREVIEW-TRACK");
    if (!tracking) return;
    updateNotice(item.id, (current) => ({ ...current, stage: "submitted", stage_label: "ارسال‌شده", progress: 100, status_label: `ارسال‌شده · ${tracking}`, documents: [...current.documents, "رسید ارسال"] }));
    notify("رکورد به ارسال‌شده منتقل شد.");
  }

  function registerNoticeResult(item: Notice) {
    const result = window.prompt("نتیجه را وارد کنید:", item.result_label || "برنده");
    if (!result) return;
    updateNotice(item.id, (current) => ({ ...current, stage: "results", stage_label: "نتایج", result_label: result, status_label: "نتیجه ثبت‌شده", next_action: result === "برنده" ? "ایجاد خودکار پیش‌نویس قرارداد" : "ثبت علت نتیجه" }));
    notify(result === "برنده" ? "نتیجه برد ثبت شد. اتصال خودکار به پیش‌نویس قرارداد در فاز قراردادها فعال خواهد شد." : "نتیجه ثبت شد.");
  }

  async function patchDirectStage(item: DirectOpportunity, stage: DirectStage, label: string) {
    if (mode === "demo") {
      setDirect((items) => items.map((current) => current.id === item.id ? { ...current, stage, stage_label: label } : current));
      notify(`فرصت به «${label}» منتقل شد.`);
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/direct-opportunities/${item.id}/`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ stage }) });
      if (!response.ok) throw new Error("تغییر مرحله فرصت انجام نشد.");
      setDirect((items) => items.map((current) => current.id === item.id ? { ...current, stage, stage_label: label } : current));
      notify(`فرصت به «${label}» منتقل شد.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "تغییر مرحله انجام نشد.");
    } finally { setBusy(false); }
  }

  async function softDeleteDirect(item: DirectOpportunity) {
    const reason = window.prompt("دلیل حذف از فهرست را ثبت کنید:", "تصمیم مدیریت");
    if (!reason) return;
    if (mode === "demo") {
      setDirect((items) => items.filter((current) => current.id !== item.id));
      notify("فرصت از فهرست Preview خارج شد؛ تاریخچه در سامانه واقعی باقی می‌ماند.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/direct-opportunities/${item.id}/soft-delete/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ reason }) });
      if (!response.ok) throw new Error("حذف از فهرست انجام نشد.");
      setDirect((items) => items.filter((current) => current.id !== item.id));
      notify("فرصت به‌صورت Soft Delete از فهرست خارج شد.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "حذف انجام نشد.");
    } finally { setBusy(false); }
  }

  async function registerDirectResult(item: DirectOpportunity) {
    const result = window.prompt("نتیجه را وارد کنید: موفق، ناموفق، متوقف‌شده یا به تعویق افتاده", item.result_label || "موفق");
    if (!result) return;
    const map: Record<string, { outcome: string; stage: DirectStage; label: string }> = {
      "موفق": { outcome: "won", stage: "won", label: "موفق" },
      "ناموفق": { outcome: "lost", stage: "lost", label: "ناموفق" },
      "متوقف‌شده": { outcome: "stopped", stage: "stopped", label: "متوقف‌شده" },
      "به تعویق افتاده": { outcome: "deferred", stage: "deferred", label: "به تعویق افتاده" },
    };
    const selected = map[result] || map["موفق"];
    if (mode === "demo") {
      setDirect((items) => items.map((current) => current.id === item.id ? { ...current, stage: selected.stage, stage_label: selected.label, result_label: selected.label, next_action: selected.stage === "won" ? "ایجاد خودکار پیش‌نویس قرارداد" : "ثبت علت نتیجه" } : current));
      notify(selected.stage === "won" ? "نتیجه موفق ثبت شد؛ اتصال به پیش‌نویس قرارداد در فاز قراردادها فعال می‌شود." : "نتیجه ثبت شد.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/opportunity-results/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ opportunity: item.id, outcome: selected.outcome, reason: "ثبت نتیجه توسط مدیر" }) });
      if (!response.ok) throw new Error("ثبت نتیجه انجام نشد.");
      setDirect((items) => items.map((current) => current.id === item.id ? { ...current, stage: selected.stage, stage_label: selected.label, result_label: selected.label } : current));
      notify("نتیجه فرصت ثبت شد.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت نتیجه انجام نشد.");
    } finally { setBusy(false); }
  }

  async function createDirect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") || "");
    const employer = String(form.get("employer") || "");
    const nextAction = String(form.get("next_action") || "");
    if (mode === "demo") {
      setDirect((items) => [{ id: `D-${Date.now()}`, title, employer_name: employer, opportunity_type: "unassigned", opportunity_type_label: "نیازمند تعیین", stage: "new", stage_label: "فرصت جدید", responsible_username: "ثبت‌کننده", next_action: nextAction, next_action_due: new Date(Date.now() + 86400000).toISOString(), probability_percent: 20, province: "", description: "فرصت جدید ثبت‌شده در Preview.", documents: [], result_label: "" }, ...items]);
      event.currentTarget.reset();
      notify("فرصت جدید در فهرست پیشنهادی ثبت شد.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/direct-opportunities/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ title, employer_name: employer, next_action: nextAction }) });
      if (!response.ok) throw new Error("ثبت فرصت انجام نشد.");
      const created = await response.json() as Record<string, unknown>;
      setDirect((items) => [{ id: String(created.id), title, employer_name: employer, opportunity_type: "unassigned", opportunity_type_label: "نیازمند تعیین", stage: "new", stage_label: "فرصت جدید", responsible_username: "ثبت‌کننده", next_action: nextAction, next_action_due: created.next_action_due ? String(created.next_action_due) : null, probability_percent: null, province: "", description: "", documents: [], result_label: "" }, ...items]);
      event.currentTarget.reset();
      notify("فرصت جدید در فهرست پیشنهادی ثبت شد.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "ثبت فرصت انجام نشد.");
    } finally { setBusy(false); }
  }

  async function saveContextDraft() {
    const nextVersion = maxContextVersion + 1;
    const payload = {
      version: nextVersion,
      status: "draft",
      role_text: editor.roleText,
      base_instructions: editor.baseInstructions,
      tender_prompt: editor.tenderPrompt,
      inquiry_prompt: editor.inquiryPrompt,
      company_profile: { summary: editor.companyProfile },
      qualifications: splitLines(editor.qualifications),
      keywords: { active: splitLines(editor.activeKeywords), excluded: splitLines(editor.excludedKeywords) },
      experience_summary: splitLines(editor.experienceSummary),
      component_versions: { role: nextVersion, prompts: nextVersion, keywords: nextVersion, company_profile: nextVersion, qualifications: nextVersion, experience: nextVersion },
      changed_components: ["role", "prompts", "keywords", "company_profile", "qualifications", "experience"],
    };
    if (mode === "demo") {
      const draft: AnalysisContext = { id: `CTX-${nextVersion}`, version: nextVersion, status: "draft", status_label: "پیش‌نویس", role_text: editor.roleText, base_instructions: editor.baseInstructions, tender_prompt: editor.tenderPrompt, inquiry_prompt: editor.inquiryPrompt, company_profile: payload.company_profile, qualifications: payload.qualifications, keywords: payload.keywords, experience_summary: payload.experience_summary, component_versions: payload.component_versions, changed_components: payload.changed_components };
      setContexts((items) => [draft, ...items]);
      setManagementView("versions");
      notify(`Snapshot پیش‌نویس نسخه ${faNumber.format(nextVersion)} ساخته شد؛ هنوز فعال نیست.`);
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/analysis-contexts/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify(payload) });
      const data = await response.json() as AnalysisContext & { detail?: string };
      if (!response.ok) throw new Error(data.detail || "ذخیره Snapshot انجام نشد.");
      setContexts((items) => [data, ...items]);
      setManagementView("versions");
      notify(`Snapshot پیش‌نویس نسخه ${faNumber.format(data.version)} ساخته شد؛ هنوز فعال نیست.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "ذخیره Snapshot انجام نشد.");
    } finally { setBusy(false); }
  }

  async function activateContext(context: AnalysisContext) {
    if (context.status !== "draft") return;
    if (!window.confirm(`نسخه ${context.version} فعال شود؟ از اجرای بعدی ChatGPT این نسخه را خواهد خواند.`)) return;
    if (mode === "demo") {
      setContexts((items) => items.map((item) => item.id === context.id ? { ...item, status: "active", status_label: "فعال", activated_at: new Date().toISOString() } : item.status === "active" ? { ...item, status: "retired", status_label: "بازنشسته" } : item));
      setEditor(contextToEditor({ ...context, status: "active", status_label: "فعال" }));
      notify(`نسخه ${faNumber.format(context.version)} فعال شد. Scheduled Task در اجرای بعدی تغییر نسخه را تشخیص می‌دهد.`);
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/analysis-contexts/${context.id}/activate/`, { method: "POST", credentials: "include", headers: { "X-CSRFToken": token } });
      if (!response.ok) throw new Error("فعال‌سازی نسخه انجام نشد.");
      const activated = await response.json() as AnalysisContext;
      setContexts((items) => items.map((item) => item.id === activated.id ? activated : item.status === "active" ? { ...item, status: "retired", status_label: "بازنشسته" } : item));
      setEditor(contextToEditor(activated));
      notify(`نسخه ${faNumber.format(activated.version)} فعال شد.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "فعال‌سازی نسخه انجام نشد.");
    } finally { setBusy(false); }
  }

  async function toggleSource(source: Source) {
    if (mode === "demo") {
      setSources((items) => items.map((item) => item.id === source.id ? { ...item, enabled: !item.enabled, status_label: item.enabled ? "غیرفعال توسط کاربر" : "فعال", connectors: item.connectors.map((connector) => ({ ...connector, enabled: item.enabled ? false : connector.key.startsWith("setad_") ? false : true })) } : item));
      notify(source.enabled ? "منبع از استخراج‌های بعدی خارج شد؛ داده قبلی حذف نمی‌شود." : "منبع فعال شد.");
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/sources/${source.id}/`, { method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ enabled: !source.enabled }) });
      if (!response.ok) throw new Error("تغییر وضعیت منبع انجام نشد.");
      setSources((items) => items.map((item) => item.id === source.id ? { ...item, enabled: !item.enabled } : item));
      notify("وضعیت منبع تغییر کرد.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "تغییر وضعیت انجام نشد.");
    } finally { setBusy(false); }
  }

  async function startExtraction() {
    if (!selectedConnectors.length) return notify("حداقل یک Connector فعال را انتخاب کنید.");
    if (mode === "demo") {
      setBusy(true);
      notify("استخراج نمایشی آغاز شد؛ هیچ اتصال واقعی انجام نمی‌شود.");
      window.setTimeout(() => { setBusy(false); notify("استخراج نمایشی پایان یافت: ۲۴ رکورد جدید و ۳ رکورد به‌روزرسانی‌شده."); }, 900);
      return;
    }
    setBusy(true);
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_BASE}/procurement/extraction-runs/`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify({ connector_ids: selectedConnectors, include_details: true, analyze_after_success: false }) });
      if (!response.ok) throw new Error("استخراج شروع نشد.");
      notify("استخراج در صف قرار گرفت.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "استخراج شروع نشد.");
    } finally { setBusy(false); }
  }

  const tabs: [Tab, string][] = [["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"], ["direct", "فرصت‌های خارج از سامانه"], ["management", "مدیریت زیرسامانه"]];
  const workflowViews: [WorkflowView, string][] = [["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"], ["submitted", "ارسال‌شده"], ["results", "نتایج"]];
  const managementViews: [ManagementView, string][] = [["extraction", "استخراج و منابع"], ["prompts", "نقش و Promptها"], ["keywords", "کلیدواژه‌ها"], ["company", "پروفایل و صلاحیت‌ها"], ["versions", "نسخه‌ها و فعال‌سازی"]];
  const detailTabs: [DetailTab, string][] = [["summary", "خلاصه"], ["followup", "پیگیری و اقدام"], ["documents", "اسناد"], ["more", "اطلاعات بیشتر"]];

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}>
      <div><span>زیرسامانه تخصصی PDP One</span><h1>فرصت‌ها و مناقصات</h1><p>مناقصات، استعلامات و فرصت‌های خارج از سامانه با یک منطق فرایندی مشترک</p></div>
      <Link href="/">بازگشت به سامانه</Link>
    </header>

    {mode !== "live" && <div className={styles.demoBanner}><b>{mode === "loading" ? "در حال بررسی اتصال..." : "حالت Preview تعاملی"}</b><span>داده‌ها نمونه‌اند و هیچ تغییری در سامانه واقعی ایجاد نمی‌شود.</span></div>}
    <nav className={styles.mainTabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setSearch(""); }}>{label}</button>)}</nav>
    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpis}>
        <article><span>فراخوان جدید</span><b>۲۴</b><small>از آخرین استخراج</small></article>
        <article><span>پیشنهادی</span><b>{faNumber.format(notices.filter((item) => noticeMatches(item, "recommended")).length + direct.filter((item) => directMatches(item, "recommended")).length)}</b><small>سه مسیر فرصت</small></article>
        <article><span>منتخب</span><b>{faNumber.format(notices.filter((item) => noticeMatches(item, "selected")).length + direct.filter((item) => directMatches(item, "selected")).length)}</b><small>در حال تصمیم و آماده‌سازی</small></article>
        <article><span>ارسال‌شده</span><b>{faNumber.format(notices.filter((item) => noticeMatches(item, "submitted")).length + direct.filter((item) => directMatches(item, "submitted")).length)}</b><small>در انتظار نتیجه</small></article>
        <article><span>نزدیک مهلت</span><b>۴</b><small>نیازمند اقدام فوری</small></article>
        <article><span>نتیجه موفق</span><b>{faNumber.format(notices.filter((item) => item.result_label === "برنده").length + direct.filter((item) => item.stage === "won").length)}</b><small>آماده پیش‌نویس قرارداد</small></article>
      </div>

      <div className={styles.dashboardGrid}>
        <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alerts}><span>۳ اقدام پیگیری عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>۴ فرصت نزدیک به مهلت</span><span>۱ ارسال‌شده بدون پیگیری نتیجه</span></div></article>
        <article className={styles.panel}><h2>قیف مدیریتی</h2><div className={styles.funnel}><span>استخراج و ثبت‌شده</span><span>پیشنهادی</span><span>منتخب</span><span>ارسال‌شده</span><span>نتیجه موفق</span></div></article>
        <article className={styles.panel}><h2>برد و باخت</h2><div className={styles.outcomeGrid}><div><b>۲</b><span>نتیجه موفق</span></div><div><b>۱</b><span>نتیجه ناموفق</span></div><div><b>۶۷٪</b><span>نرخ موفقیت نمونه</span></div><div><b>۲</b><span>پیش‌نویس قرارداد آینده</span></div></div></article>
        <article className={styles.panel}><h2>جمع‌بندی مدیریتی ChatGPT</h2><p>طرح جامع فارس بالاترین تناسب را دارد. استعلام نقشه‌برداری تهران فوریت بحرانی دارد. دو نتیجه موفق پس از تکمیل ماژول قراردادها باید خودکار به پیش‌نویس قرارداد تبدیل شوند.</p><div className={styles.tags}><span>اقدام امروز: استعلام تهران</span><span>فرصت راهبردی: طرح جامع فارس</span><span>پیگیری: پیشنهاد درمانی</span></div></article>
      </div>

      <article className={`${styles.panel} ${styles.activeCases}`}><div className={styles.panelHeader}><div><span>پایین صفحه داشبورد</span><h2>پرونده‌های فعال</h2></div><small>منتخب و ارسال‌شده از هر سه مسیر</small></div><div className={styles.caseTable}>
        {activeCases.map((item) => { const itemUrgency = urgency(item.deadline); return <button key={item.id} onClick={() => openDetail({ type: "notice", item })}><span><b>{item.title}</b><small>{item.employer_name} · {item.kind === "tender" ? "مناقصه" : "استعلام"}</small></span><span><b>{item.stage_label}</b><small>{item.next_action}</small></span><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}><b>{itemUrgency.label}</b><small>{itemUrgency.remaining}</small></span></button>; })}
        {direct.filter((item) => directMatches(item, "selected") || directMatches(item, "submitted")).map((item) => { const itemUrgency = urgency(item.next_action_due); return <button key={item.id} onClick={() => openDetail({ type: "direct", item })}><span><b>{item.title}</b><small>{item.employer_name} · فرصت خارج از سامانه</small></span><span><b>{item.stage_label}</b><small>{item.next_action}</small></span><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}><b>{itemUrgency.label}</b><small>{itemUrgency.remaining}</small></span></button>; })}
      </div></article>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <SectionHeading eyebrow={tab === "tenders" ? "فرآیند مناقصات" : "فرآیند استعلامات"} title={tab === "tenders" ? "مناقصات" : "استعلامات"} description="پیشنهادی، منتخب، ارسال‌شده و نتایج با عملیات متناسب هر مرحله نمایش داده می‌شوند." />
      <WorkflowTabs value={noticeView} onChange={setNoticeView} items={workflowViews} />
      <SearchToolbar value={search} onChange={setSearch} count={visibleNotices.length} />
      <div className={styles.list}>{visibleNotices.map((item) => <NoticeCard key={item.id} item={item} view={noticeView} onOpen={() => openDetail({ type: "notice", item })} onSelect={() => selectNotice(item)} onRemove={() => removeNoticeFromCurrent(item, noticeView === "selected")} onSubmit={() => markNoticeSubmitted(item)} onResult={() => registerNoticeResult(item)} onNotify={notify} />)}{!visibleNotices.length && <EmptyState />}</div>
    </section>}

    {tab === "direct" && <section>
      <SectionHeading eyebrow="فرآیند فرصت‌های خارج از سامانه" title="فرصت‌های خارج از سامانه" description="این بخش دقیقاً مانند مناقصات و استعلامات دارای پیشنهادی، منتخب، ارسال‌شده و نتایج است." />
      <form className={styles.quickForm} onSubmit={createDirect}><label>عنوان فرصت<input name="title" required /></label><label>کارفرما<input name="employer" required /></label><label>اقدام بعدی<input name="next_action" required /></label><button disabled={busy}>ثبت در پیشنهادی</button></form>
      <WorkflowTabs value={directView} onChange={setDirectView} items={workflowViews} />
      <SearchToolbar value={search} onChange={setSearch} count={visibleDirect.length} />
      <div className={styles.list}>{visibleDirect.map((item) => <DirectCard key={item.id} item={item} view={directView} onOpen={() => openDetail({ type: "direct", item })} onSelect={() => patchDirectStage(item, "selected", "منتخب")} onRemove={() => softDeleteDirect(item)} onPrepare={() => patchDirectStage(item, "preparing", "در دست تهیه پیشنهاد")} onSubmit={() => patchDirectStage(item, "submitted", "پیشنهاد ارسال‌شده")} onResult={() => registerDirectResult(item)} onNotify={notify} />)}{!visibleDirect.length && <EmptyState />}</div>
    </section>}

    {tab === "management" && <section>
      <SectionHeading eyebrow="تنظیمات زیرسامانه" title="مدیریت زیرسامانه" description="منابع استخراج و تمام اطلاعاتی که ChatGPT می‌خواند از این بخش مدیریت و نسخه‌بندی می‌شوند." />
      <div className={styles.managementTabs}>{managementViews.map(([id, label]) => <button key={id} className={managementView === id ? styles.selected : ""} onClick={() => setManagementView(id)}>{label}</button>)}</div>

      {managementView === "extraction" && <div className={styles.managementGrid}>
        <article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.sourceList}>{sources.map((source) => <div key={source.id}><label><input type="checkbox" checked={source.enabled} disabled={busy} onChange={() => toggleSource(source)} /><b>{source.name}</b></label><span>{source.status_label}</span><small>{source.connectors.map((connector) => `${connector.notice_type_label}: ${connector.enabled ? "فعال" : "غیرفعال"}`).join(" · ")}</small></div>)}</div></article>
        <article className={styles.panel}><h2>اجرای استخراج</h2><div className={styles.connectorList}>{sources.flatMap((source) => source.connectors).map((connector) => <label key={connector.id}><input type="checkbox" checked={selectedConnectors.includes(connector.id)} disabled={!connector.enabled || busy} onChange={(event) => setSelectedConnectors((items) => event.target.checked ? [...new Set([...items, connector.id])] : items.filter((id) => id !== connector.id))} /><span>{connector.key}</span><small>{connector.status_label}</small></label>)}</div><button className={styles.primaryButton} disabled={busy} onClick={startExtraction}>شروع استخراج منابع انتخاب‌شده</button></article>
        <article className={styles.panel}><h2>زمان‌بندی</h2><dl><div><dt>وضعیت</dt><dd>{automation.enabled ? "فعال" : "غیرفعال تا تأیید Preview"}</dd></div><div><dt>دوره</dt><dd>{automation.cadence_label}</dd></div><div><dt>ساعت</dt><dd>{automation.daily_time || "تعیین نشده"}</dd></div><div><dt>تأخیر تحلیل</dt><dd>{faNumber.format(automation.analysis_delay_minutes)} دقیقه</dd></div><div><dt>فرمان دستی</dt><dd>{automation.manual_command}</dd></div></dl></article>
        <article className={styles.panel}><h2>وضعیت اتصال تحلیل</h2><div className={styles.alerts}><span>ChatGPT در هر اجرا ابتدا Manifest نسخه را می‌خواند.</span><span>Snapshot کامل فقط هنگام تغییر نسخه دریافت می‌شود.</span><span>Scheduled Task با Connected App باید در Preview عملیاتی آزمایش شود.</span></div></article>
      </div>}

      {managementView === "prompts" && <div className={styles.editorGrid}>
        <EditorField label="نقش تخصصی فعال" value={editor.roleText} onChange={(value) => updateEditor("roleText", value)} rows={4} help="تعریف می‌کند ChatGPT در این گردش کار چه نقشی دارد." />
        <EditorField label="دستورهای پایه تحلیل" value={editor.baseInstructions} onChange={(value) => updateEditor("baseInstructions", value)} rows={6} help="قواعد مشترک، محدودیت‌ها و Draft-first بودن نتیجه." />
        <EditorField label="Prompt تحلیل مناقصات" value={editor.tenderPrompt} onChange={(value) => updateEditor("tenderPrompt", value)} rows={7} help="دستور اختصاصی ارزیابی مناقصه." />
        <EditorField label="Prompt تحلیل استعلامات" value={editor.inquiryPrompt} onChange={(value) => updateEditor("inquiryPrompt", value)} rows={7} help="دستور اختصاصی ارزیابی استعلام با تأکید بر فوریت." />
        <SaveBar onSave={saveContextDraft} busy={busy} />
      </div>}

      {managementView === "keywords" && <div className={styles.editorGrid}>
        <EditorField label="کلیدواژه‌های فعال" value={editor.activeKeywords} onChange={(value) => updateEditor("activeKeywords", value)} rows={12} help="هر کلیدواژه در یک خط؛ کلیدواژه‌ها زمینه تحلیل‌اند و امتیاز جبری ایجاد نمی‌کنند." />
        <EditorField label="کلیدواژه‌های حذف یا احتیاط" value={editor.excludedKeywords} onChange={(value) => updateEditor("excludedKeywords", value)} rows={12} help="موضوعاتی که معمولاً نامرتبط‌اند یا نیازمند احتیاط بیشتر هستند." />
        <article className={styles.panel}><h2>قاعده استفاده</h2><p>ChatGPT کلیدواژه‌ها را همراه با رزومه، صلاحیت، زمان، ریسک و ظرفیت شرکت بررسی می‌کند. وجود یک کلمه به‌تنهایی باعث پیشنهاد یا رد خودکار نمی‌شود.</p></article>
        <SaveBar onSave={saveContextDraft} busy={busy} />
      </div>}

      {managementView === "company" && <div className={styles.editorGrid}>
        <EditorField label="پروفایل خلاصه شرکت" value={editor.companyProfile} onChange={(value) => updateEditor("companyProfile", value)} rows={8} help="شناخت کلی شرکت که در همه تحلیل‌ها استفاده می‌شود." />
        <EditorField label="صلاحیت‌ها و رتبه‌ها" value={editor.qualifications} onChange={(value) => updateEditor("qualifications", value)} rows={10} help="هر صلاحیت یا رتبه در یک خط." />
        <EditorField label="خلاصه سوابق و تجربه‌ها" value={editor.experienceSummary} onChange={(value) => updateEditor("experienceSummary", value)} rows={10} help="خلاصه سوابق؛ جزئیات پروژه مرتبط فقط هنگام نیاز خوانده می‌شود." />
        <article className={styles.panel}><h2>نحوه استفاده در تحلیل</h2><p>این اطلاعات در Snapshot نسخه‌بندی‌شده ذخیره می‌شوند. Scheduled Task فقط هنگام تغییر نسخه، محتوای جدید را دریافت می‌کند.</p></article>
        <SaveBar onSave={saveContextDraft} busy={busy} />
      </div>}

      {managementView === "versions" && <div className={styles.versionLayout}>
        <article className={styles.panel}><h2>نسخه فعال</h2><dl><div><dt>نسخه</dt><dd>{faNumber.format(activeContext.version)}</dd></div><div><dt>وضعیت</dt><dd>{activeContext.status_label}</dd></div><div><dt>فعال‌سازی</dt><dd>{displayDateTime(activeContext.activated_at || null)}</dd></div><div><dt>Prompt</dt><dd>نسخه {faNumber.format(activeContext.component_versions.prompts || activeContext.version)}</dd></div><div><dt>کلیدواژه‌ها</dt><dd>نسخه {faNumber.format(activeContext.component_versions.keywords || activeContext.version)}</dd></div></dl><button className={styles.secondaryButton} onClick={() => setEditor(contextToEditor(activeContext))}>بارگذاری نسخه فعال در ویرایشگر</button></article>
        <article className={styles.panel}><h2>پیش‌نویس‌های آماده بررسی</h2><div className={styles.versionList}>{draftContexts.map((context) => <div key={context.id}><span><b>نسخه {faNumber.format(context.version)}</b><small>{context.changed_components.join("، ") || "تغییرات کامل"}</small></span><button disabled={busy} onClick={() => activateContext(context)}>فعال‌سازی نسخه</button></div>)}{!draftContexts.length && <p>پیش‌نویس جدیدی وجود ندارد.</p>}</div></article>
        <article className={`${styles.panel} ${styles.versionHistory}`}><h2>تاریخچه نسخه‌ها</h2><div className={styles.historyTable}>{contexts.sort((a, b) => b.version - a.version).map((context) => <div key={context.id}><b>نسخه {faNumber.format(context.version)}</b><span>{context.status_label}</span><small>{context.status === "active" ? "مبنای اجرای فعلی ChatGPT" : context.status === "draft" ? "نیازمند فعال‌سازی مدیر" : "نسخه قبلی"}</small></div>)}</div></article>
      </div>}
    </section>}

    {selectedDetail && <DetailModal selected={selectedDetail} tab={detailTab} tabs={detailTabs} onTab={setDetailTab} onClose={() => setSelectedDetail(null)} onNotify={notify} />}
  </main>;
}

function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className={styles.sectionHeading}><div><span>{eyebrow}</span><h2>{title}</h2></div><small>{description}</small></div>;
}

function WorkflowTabs({ value, onChange, items }: { value: WorkflowView; onChange: (value: WorkflowView) => void; items: [WorkflowView, string][] }) {
  return <div className={styles.workflowTabs}>{items.map(([id, label]) => <button key={id} className={value === id ? styles.selected : ""} onClick={() => onChange(id)}>{label}</button>)}</div>;
}

function SearchToolbar({ value, onChange, count }: { value: string; onChange: (value: string) => void; count: number }) {
  return <div className={styles.toolbar}><input value={value} onChange={(event) => onChange(event.target.value)} placeholder="عنوان، کارفرما، استان یا منبع..." /><span>{faNumber.format(count)} رکورد</span></div>;
}

function EmptyState() {
  return <div className={styles.empty}>رکوردی مطابق این نما وجود ندارد.</div>;
}

function NoticeCard({ item, view, onOpen, onSelect, onRemove, onSubmit, onResult, onNotify }: { item: Notice; view: WorkflowView; onOpen: () => void; onSelect: () => void; onRemove: () => void; onSubmit: () => void; onResult: () => void; onNotify: (text: string) => void }) {
  const itemUrgency = urgency(item.deadline);
  return <article className={styles.recordCard}><div className={styles.recordMain}><div className={styles.recordTop}><small>{item.source_label} · {item.province} · {item.status_label}</small><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}>{itemUrgency.label}</span></div><h3>{item.title}</h3><p>{item.employer_name}</p><div className={styles.facts}><span>انتشار: {displayDate(item.published_at)}</span><span>مهلت: {displayDateTime(item.deadline)}</span><span>{itemUrgency.remaining}</span></div>{item.missing_information.length ? <div className={styles.missing}>نقص اطلاعات: {item.missing_information.join("، ")}</div> : null}</div><div className={styles.recordDecision}><span className={styles.stage}>{item.result_label || item.stage_label || (item.recommended ? "پیشنهادی" : "در انتظار تحلیل")}</span><dl><div><dt>اولویت</dt><dd>{item.score == null ? "تحلیل نشده" : `${faNumber.format(item.score)} از ۱۰۰`}</dd></div><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.next_action || "تعیین نشده"}</dd></div></dl><div className={styles.actions}><button onClick={onOpen}>مشاهده</button>{view === "recommended" && <><button className={styles.primaryAction} onClick={onSelect}>انتخاب</button><button className={styles.dangerAction} onClick={onRemove}>حذف</button></>}{view === "selected" && <><button onClick={() => onNotify("پیگیری در Preview ثبت شد.")}>پیگیری</button><button onClick={() => onNotify("پیشرفت آماده‌سازی در Preview به‌روزرسانی شد.")}>ثبت پیشرفت</button><button className={styles.primaryAction} onClick={onSubmit}>ارسال شد</button><button className={styles.dangerAction} onClick={onRemove}>حذف</button></>}{view === "submitted" && <><button className={styles.primaryAction} onClick={onResult}>ثبت نتیجه</button><button onClick={() => onNotify("پیگیری نتیجه ثبت شد.")}>ثبت پیگیری</button></>}{view === "results" && <><button onClick={onResult}>اصلاح نتیجه</button><button onClick={() => onNotify(item.result_label === "برنده" ? "پیش‌نویس قرارداد در ماژول قراردادها ایجاد خواهد شد." : "فقط نتیجه موفق وارد پیش‌نویس قرارداد می‌شود.")}>پیش‌نویس قرارداد</button></>}</div></div></article>;
}

function DirectCard({ item, view, onOpen, onSelect, onRemove, onPrepare, onSubmit, onResult, onNotify }: { item: DirectOpportunity; view: WorkflowView; onOpen: () => void; onSelect: () => void; onRemove: () => void; onPrepare: () => void; onSubmit: () => void; onResult: () => void; onNotify: (text: string) => void }) {
  const itemUrgency = urgency(item.next_action_due);
  return <article className={styles.recordCard}><div className={styles.recordMain}><div className={styles.recordTop}><small>{item.opportunity_type_label} · {item.province || "استان نامشخص"}</small><span className={`${styles.urgency} ${styles[itemUrgency.tone]}`}>{itemUrgency.label}</span></div><h3>{item.title}</h3><p>{item.employer_name}</p><div className={styles.facts}><span>اقدام بعدی: {item.next_action}</span><span>{itemUrgency.remaining}</span><span>احتمال تبدیل: {item.probability_percent == null ? "نامشخص" : `${faNumber.format(item.probability_percent)}٪`}</span></div></div><div className={styles.recordDecision}><span className={styles.stage}>{item.result_label || item.stage_label}</span><dl><div><dt>مسئول</dt><dd>{item.responsible_username || "تعیین نشده"}</dd></div><div><dt>تاریخ اقدام</dt><dd>{displayDateTime(item.next_action_due)}</dd></div></dl><div className={styles.actions}><button onClick={onOpen}>مشاهده</button>{view === "recommended" && <><button className={styles.primaryAction} onClick={onSelect}>انتخاب</button><button onClick={() => onNotify("پیگیری فرصت ثبت شد.")}>پیگیری</button><button className={styles.dangerAction} onClick={onRemove}>حذف</button></>}{view === "selected" && <><button onClick={() => onNotify("پیگیری فرصت ثبت شد.")}>پیگیری</button><button onClick={onPrepare}>در دست تهیه</button><button className={styles.primaryAction} onClick={onSubmit}>ارسال شد</button><button className={styles.dangerAction} onClick={onRemove}>حذف</button></>}{view === "submitted" && <><button className={styles.primaryAction} onClick={onResult}>ثبت نتیجه</button><button onClick={() => onNotify("پیگیری نتیجه ثبت شد.")}>ثبت پیگیری</button></>}{view === "results" && <><button onClick={onResult}>اصلاح نتیجه</button><button onClick={() => onNotify(item.stage === "won" ? "در فاز قراردادها، پیش‌نویس قرارداد خودکار ایجاد می‌شود." : "فقط نتیجه موفق وارد قرارداد می‌شود.")}>پیش‌نویس قرارداد</button></>}</div></div></article>;
}

function EditorField({ label, value, onChange, rows, help }: { label: string; value: string; onChange: (value: string) => void; rows: number; help: string }) {
  return <label className={styles.editorField}><span>{label}</span><textarea value={value} rows={rows} onChange={(event) => onChange(event.target.value)} /><small>{help}</small></label>;
}

function SaveBar({ onSave, busy }: { onSave: () => void; busy: boolean }) {
  return <div className={styles.saveBar}><div><b>ذخیره مستقیم روی نسخه فعال انجام نمی‌شود.</b><small>ابتدا Snapshot پیش‌نویس ساخته و سپس مدیر آن را فعال می‌کند.</small></div><button disabled={busy} onClick={onSave}>ذخیره به‌عنوان نسخه پیش‌نویس</button></div>;
}

function DetailModal({ selected, tab, tabs, onTab, onClose, onNotify }: { selected: Exclude<SelectedDetail, null>; tab: DetailTab; tabs: [DetailTab, string][]; onTab: (tab: DetailTab) => void; onClose: () => void; onNotify: (text: string) => void }) {
  const title = selected.item.title;
  const employer = selected.item.employer_name;
  return <div className={styles.modalBackdrop} role="presentation" onMouseDown={onClose}><section className={styles.modal} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><small>{selected.type === "notice" ? "جزئیات فراخوان" : "جزئیات فرصت خارج از سامانه"}</small><h2>{title}</h2><p>{employer}</p></div><button onClick={onClose} aria-label="بستن">×</button></header><nav>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.selected : ""} onClick={() => onTab(id)}>{label}</button>)}</nav><div className={styles.modalBody}>{selected.type === "notice" ? <NoticeDetail item={selected.item} tab={tab} onNotify={onNotify} /> : <DirectDetail item={selected.item} tab={tab} onNotify={onNotify} />}</div></section></div>;
}

function NoticeDetail({ item, tab, onNotify }: { item: Notice; tab: DetailTab; onNotify: (text: string) => void }) {
  const itemUrgency = urgency(item.deadline);
  if (tab === "summary") return <><div className={styles.detailKpis}><article><span>مهلت</span><b>{displayDateTime(item.deadline)}</b><small>{itemUrgency.remaining}</small></article><article><span>فوریت</span><b>{itemUrgency.label}</b><small>بر مبنای زمان باقی‌مانده</small></article><article><span>اولویت</span><b>{item.score == null ? "تحلیل نشده" : `${faNumber.format(item.score)} / ۱۰۰`}</b><small>تحلیل ChatGPT</small></article><article><span>وضعیت</span><b>{item.result_label || item.stage_label || (item.recommended ? "پیشنهادی" : "ثبت‌شده")}</b><small>{item.status_label}</small></article></div><div className={styles.detailColumns}><article><h3>اطلاعات فراخوان</h3><dl><div><dt>کارفرما</dt><dd>{item.employer_name}</dd></div><div><dt>استان</dt><dd>{item.province}</dd></div><div><dt>منبع</dt><dd>{item.source_label}</dd></div><div><dt>تاریخ انتشار</dt><dd>{displayDate(item.published_at)}</dd></div></dl></article><article><h3>جمع‌بندی تحلیل</h3><p><b>دلیل پیشنهاد:</b> {item.recommendation_reason}</p><p><b>ریسک:</b> {item.risk_notes}</p></article></div></>;
  if (tab === "followup") return <div className={styles.detailColumns}><article><h3>پیگیری</h3><dl><div><dt>مسئول</dt><dd>{item.responsible || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.next_action}</dd></div><div><dt>تاریخ اقدام</dt><dd>{displayDateTime(item.next_action_due)}</dd></div><div><dt>پیشرفت</dt><dd>{faNumber.format(item.progress)}٪</dd></div></dl><div className={styles.progress}><span style={{ width: `${item.progress}%` }} /></div></article><article><h3>نتیجه و انتقال</h3><p>{item.result_label ? `نتیجه: ${item.result_label}` : "نتیجه هنوز ثبت نشده است."}</p>{item.result_label === "برنده" && <button className={styles.primaryButton} onClick={() => onNotify("در فاز قراردادها، پیش‌نویس قرارداد خودکار ساخته خواهد شد.")}>مشاهده مسیر پیش‌نویس قرارداد</button>}</article></div>;
  if (tab === "documents") return <div className={styles.detailColumns}><article><h3>اسناد</h3><div className={styles.documentList}>{item.documents.map((document) => <button key={document}><b>{document}</b><small>فایل خصوصی سامانه</small></button>)}</div></article><article><h3>نقص اطلاعات</h3><div className={styles.alerts}>{item.missing_information.length ? item.missing_information.map((value) => <span key={value}>{value}</span>) : <span className={styles.success}>نقصی ثبت نشده است.</span>}</div></article></div>;
  return <div className={styles.detailColumns}><article><h3>شرح</h3><p>{item.description}</p></article><article><h3>اطلاعات مالی</h3><dl><div><dt>مبلغ برآورد</dt><dd>{item.estimated_amount}</dd></div><div><dt>تضمین</dt><dd>{item.guarantee}</dd></div></dl></article></div>;
}

function DirectDetail({ item, tab, onNotify }: { item: DirectOpportunity; tab: DetailTab; onNotify: (text: string) => void }) {
  const itemUrgency = urgency(item.next_action_due);
  if (tab === "summary") return <div className={styles.detailColumns}><article><h3>خلاصه فرصت</h3><dl><div><dt>نوع</dt><dd>{item.opportunity_type_label}</dd></div><div><dt>مرحله</dt><dd>{item.stage_label}</dd></div><div><dt>مسئول</dt><dd>{item.responsible_username || "تعیین نشده"}</dd></div><div><dt>احتمال تبدیل</dt><dd>{item.probability_percent == null ? "نامشخص" : `${faNumber.format(item.probability_percent)}٪`}</dd></div></dl></article><article><h3>شرح</h3><p>{item.description || "شرح تکمیلی ثبت نشده است."}</p></article></div>;
  if (tab === "followup") return <div className={styles.detailColumns}><article><h3>اقدام بعدی</h3><dl><div><dt>اقدام</dt><dd>{item.next_action}</dd></div><div><dt>تاریخ</dt><dd>{displayDateTime(item.next_action_due)}</dd></div><div><dt>فوریت</dt><dd>{itemUrgency.label}</dd></div></dl></article><article><h3>مسیر فرایند</h3><p>پیشنهادی → منتخب → ارسال‌شده → نتایج</p></article></div>;
  if (tab === "documents") return <div className={styles.documentList}>{item.documents.length ? item.documents.map((document) => <button key={document}><b>{document}</b><small>فایل خصوصی سامانه</small></button>) : <p>سندی ثبت نشده است.</p>}</div>;
  return <div className={styles.detailColumns}><article><h3>تبدیل‌ها</h3><p>فرصت می‌تواند به مناقصه، استعلام یا پس از نتیجه موفق به پیش‌نویس قرارداد تبدیل شود.</p></article><article><h3>قرارداد آینده</h3><button className={styles.primaryButton} onClick={() => onNotify(item.stage === "won" ? "پیش‌نویس قرارداد در فاز قراردادها خودکار ایجاد خواهد شد." : "ابتدا باید نتیجه موفق ثبت شود.")}>بررسی مسیر قرارداد</button></article></div>;
}
