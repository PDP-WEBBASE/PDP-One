"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./procurement.module.css";

type Tab = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
type NoticeView = "all" | "recommended" | "selected" | "submitted" | "results";
type DetailSection = "summary" | "followup" | "documents" | "more";
type DataMode = "loading" | "live" | "demo";

type SubmissionInfo = {
  sent_at?: string | null;
  method?: string;
  tracking_code?: string;
  recipient?: string;
  proposed_amount?: string;
  result_followup_at?: string | null;
};

type Notice = {
  id: string;
  title: string;
  employer_name: string;
  province: string;
  city?: string;
  execution_location?: string;
  notice_number?: string;
  source_label?: string;
  source_count?: number;
  published_date?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  submission_deadline: string | null;
  processing_status_label: string;
  is_recommended: boolean;
  case_stage_label?: string | null;
  result_label?: string | null;
  recommendation_score?: number;
  recommendation_reason?: string;
  analysis_risk?: string;
  suggested_action?: string;
  confidence_label?: string;
  responsible_username?: string;
  next_action?: string;
  next_action_due?: string | null;
  internal_deadline?: string | null;
  preparation_status?: string;
  progress?: number;
  documents?: string[];
  missing_information?: string[];
  summary?: string;
  description?: string;
  conditions?: string;
  qualification_text?: string;
  estimated_amount_label?: string;
  guarantee_label?: string;
  contact_text?: string;
  similar_experience?: string[];
  analysis_summary?: string;
  submission_info?: SubmissionInfo;
};

type ApiNotice = Notice & {
  case?: {
    stage_label?: string;
    responsible_username?: string;
    next_action?: string;
    next_action_due?: string | null;
    progress?: number;
  } | null;
  source_links?: Array<{ source_notice?: { source_name?: string } }>;
  estimated_amount_rials?: string | null;
  guarantee_amount_rials?: string | null;
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
  opportunity_type?: string;
  responsible_username?: string;
  last_activity_at?: string | null;
  probability?: number;
  risk_label?: string;
  description?: string;
  documents?: string[];
  notes?: string[];
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

type Urgency = { label: string; remaining: string; tone: "critical" | "high" | "medium" | "normal" | "unknown" };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const faNumber = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "short", day: "numeric" });
const faDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

const seedDashboard: Dashboard = {
  notices: { total: 186, tenders: 118, inquiries: 68, recommended: 17, deadline_passed: 9 },
  cases: { active: 12, overdue_next_actions: 3, without_responsible: 2 },
  sources: { enabled_sites: 2, enabled_connectors: 4, pending_connectors: 2 },
};

const sharedNoticeDefaults = {
  documents: ["آگهی اصلی", "شرایط شرکت در فراخوان"],
  missing_information: ["مبلغ برآورد در منبع درج نشده است"],
  confidence_label: "اطمینان بالا",
  qualification_text: "صلاحیت مشاوره مرتبط و ارائه سوابق مشابه الزامی است.",
  contact_text: "اطلاعات تماس در آگهی اصلی منبع قابل مشاهده است.",
  similar_experience: ["پروژه‌های معماری و شهرسازی مشابه", "سوابق طراحی و نظارت شرکت"],
};

const seedTenders: Notice[] = [
  {
    ...sharedNoticeDefaults,
    id: "T-001", title: "خدمات مشاوره طراحی و نظارت مجموعه اداری", employer_name: "شرکت توسعه عمران", province: "تهران", city: "تهران", execution_location: "منطقه مرکزی تهران", notice_number: "10950416", source_label: "هزاره", source_count: 1,
    published_date: "2026-07-21T08:00:00+03:30", last_seen_at: "2026-07-22T17:12:00+03:30", submission_deadline: "2026-07-25T16:00:00+03:30", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب",
    recommendation_score: 91, recommendation_reason: "انطباق مستقیم با رتبه معماری و سابقه طراحی و نظارت شرکت.", analysis_risk: "زمان تهیه پیشنهاد محدود و نیازمند تعیین سریع تیم است.", suggested_action: "تعیین مدیر پیشنهاد و بررسی فوری اسناد مالی.", responsible_username: "محمد ملکی", next_action: "تقسیم کار تهیه پیشنهاد", next_action_due: "2026-07-23T10:00:00+03:30", internal_deadline: "2026-07-24T12:00:00+03:30", preparation_status: "در حال جمع‌آوری اسناد", progress: 35,
    summary: "خدمات طراحی و نظارت یک مجموعه اداری با تمرکز بر معماری و هماهنگی تأسیسات.", description: "شرح خدمات شامل مطالعات اولیه، طراحی مراحل یک و دو و نظارت بر اجرا است.", conditions: "ارائه تیم کلیدی، سوابق مشابه و تضمین شرکت در فرایند انتخاب.", estimated_amount_label: "در اسناد اعلام می‌شود", guarantee_label: "نیازمند بررسی اسناد", analysis_summary: "فرصت مناسب با اولویت زیاد؛ شرط موفقیت، آماده‌سازی سریع تیم و مستندات سوابق است.",
  },
  {
    ...sharedNoticeDefaults,
    id: "T-002", title: "مطالعات طرح جامع و برنامه‌ریزی فضایی", employer_name: "اداره کل راه و شهرسازی", province: "فارس", city: "شیراز", execution_location: "استان فارس", notice_number: "F-1405-88", source_label: "پارس نماد داده", source_count: 2,
    published_date: "2026-07-20T09:30:00+03:30", last_seen_at: "2026-07-22T17:10:00+03:30", submission_deadline: "2026-07-30T14:00:00+03:30", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب",
    recommendation_score: 95, recommendation_reason: "هم‌راستا با رتبه مطالعات جغرافیایی و برنامه‌ریزی فضایی شرکت.", analysis_risk: "حجم مطالعات و نیاز به تیم چندتخصصی بالا است.", suggested_action: "بررسی ظرفیت تیم برنامه‌ریزی و انتخاب شریک تخصصی در صورت نیاز.", responsible_username: "کارشناس مناقصات", next_action: "تهیه ساختار شکست خدمات", next_action_due: "2026-07-24T11:00:00+03:30", internal_deadline: "2026-07-28T12:00:00+03:30", preparation_status: "در حال تهیه پیشنهاد فنی", progress: 62,
    summary: "مطالعات طرح جامع با ابعاد کالبدی، اقتصادی و برنامه‌ریزی فضایی.", description: "خدمات شامل شناخت، تحلیل وضع موجود، سناریوسازی و ارائه برنامه اجرایی است.", conditions: "تیم چندرشته‌ای و سوابق مطالعات منطقه‌ای الزامی است.", estimated_amount_label: "حدود ۴۵ میلیارد ریال", guarantee_label: "۲ میلیارد ریال", analysis_summary: "از بهترین فرصت‌های جاری شرکت با تناسب تخصصی بسیار زیاد است.",
  },
  {
    ...sharedNoticeDefaults,
    id: "T-003", title: "طراحی تأسیسات مکانیکی و برقی بیمارستان", employer_name: "دانشگاه علوم پزشکی", province: "البرز", city: "کرج", execution_location: "کرج", notice_number: "MED-1405-31", source_label: "هزاره", source_count: 1,
    published_date: "2026-07-22T07:20:00+03:30", last_seen_at: "2026-07-22T17:12:00+03:30", submission_deadline: "2026-07-27T12:00:00+03:30", processing_status_label: "در انتظار تحلیل", is_recommended: false, case_stage_label: null,
    recommendation_score: 0, recommendation_reason: "تحلیل ChatGPT هنوز انجام نشده است.", analysis_risk: "اطلاعات جزئیات مناقصه ناقص است.", suggested_action: "دریافت جزئیات و اجرای تحلیل.", summary: "طراحی تأسیسات یک بیمارستان جدید.", description: "اطلاعات تکمیلی پس از دریافت صفحه جزئیات منبع نمایش داده می‌شود.", conditions: "نامشخص", estimated_amount_label: "نامشخص", guarantee_label: "نامشخص", analysis_summary: "در انتظار تحلیل.",
  },
  {
    ...sharedNoticeDefaults,
    id: "T-004", title: "مطالعات امکان‌سنجی شهرک صنعتی", employer_name: "شرکت شهرک‌های صنعتی", province: "آذربایجان شرقی", city: "تبریز", execution_location: "حومه تبریز", notice_number: "IND-2201", source_label: "پارس نماد داده", source_count: 1,
    published_date: "2026-07-15T09:00:00+03:30", last_seen_at: "2026-07-21T17:00:00+03:30", submission_deadline: "2026-07-22T15:00:00+03:30", processing_status_label: "ارسال‌شده", is_recommended: true, case_stage_label: "ارسال‌شده",
    recommendation_score: 82, recommendation_reason: "تناسب با پروانه فنی و مهندسی صنعت و معدن.", analysis_risk: "رقابت زیاد و حساسیت مالی پیشنهاد.", suggested_action: "پیگیری تأیید دریافت پیشنهاد.", responsible_username: "واحد توسعه کسب‌وکار", next_action: "پیگیری نتیجه اولیه", next_action_due: "2026-07-26T09:00:00+03:30", internal_deadline: "2026-07-22T12:00:00+03:30", preparation_status: "ارسال تکمیل شده", progress: 100,
    submission_info: { sent_at: "2026-07-22T11:40:00+03:30", method: "سامانه کارفرما", tracking_code: "TRK-84291", recipient: "دبیرخانه معاملات", proposed_amount: "۳۸ میلیارد ریال", result_followup_at: "2026-07-26T09:00:00+03:30" },
    summary: "امکان‌سنجی فنی، اقتصادی و مکانی شهرک صنعتی.", description: "پیشنهاد فنی و مالی از طریق سامانه کارفرما ارسال شده است.", conditions: "سوابق صنعتی و تیم اقتصادی الزامی بود.", estimated_amount_label: "۳۸ میلیارد ریال پیشنهادی", guarantee_label: "۱.۵ میلیارد ریال", analysis_summary: "پیشنهاد ارسال شده و اکنون نیازمند پیگیری نتیجه است.", documents: ["آگهی اصلی", "پیشنهاد فنی", "پیشنهاد مالی", "رسید ارسال"], missing_information: [],
  },
  {
    ...sharedNoticeDefaults,
    id: "T-005", title: "خدمات طراحی معماری مجتمع آموزشی", employer_name: "سازمان نوسازی مدارس", province: "قم", city: "قم", execution_location: "استان قم", notice_number: "EDU-177", source_label: "هزاره", source_count: 1,
    published_date: "2026-06-30T08:00:00+03:30", last_seen_at: "2026-07-20T17:00:00+03:30", submission_deadline: "2026-07-10T12:00:00+03:30", processing_status_label: "نتیجه ثبت‌شده", is_recommended: true, case_stage_label: "نتایج", result_label: "برنده",
    recommendation_score: 94, recommendation_reason: "سابقه و رتبه مستقیم در پروژه‌های آموزشی.", analysis_risk: "ریسک اصلی کنترل برنامه زمانی قرارداد است.", suggested_action: "تبدیل پرونده به قرارداد و آغاز برنامه تجهیز تیم.", responsible_username: "مدیرعامل", next_action: "تکمیل اطلاعات قرارداد", next_action_due: "2026-07-24T10:00:00+03:30", preparation_status: "نتیجه نهایی", progress: 100,
    submission_info: { sent_at: "2026-07-09T10:20:00+03:30", method: "پاکت فیزیکی", tracking_code: "REC-1405-118", recipient: "دبیرخانه سازمان", proposed_amount: "۶۲ میلیارد ریال", result_followup_at: null },
    summary: "طراحی معماری مجتمع آموزشی و محوطه وابسته.", description: "شرکت به‌عنوان برنده انتخاب شده است.", conditions: "رتبه معماری آموزشی و ارائه سوابق مشابه.", estimated_amount_label: "۶۲ میلیارد ریال", guarantee_label: "۳ میلیارد ریال", analysis_summary: "فرصت به نتیجه موفق رسیده و آماده تبدیل به قرارداد است.", documents: ["آگهی اصلی", "پیشنهاد فنی", "پیشنهاد مالی", "اعلام برنده"], missing_information: [],
  },
];

const seedInquiries: Notice[] = [
  {
    ...sharedNoticeDefaults,
    id: "I-001", title: "استعلام خدمات نقشه‌برداری و برداشت وضع موجود", employer_name: "شهرداری منطقه", province: "تهران", city: "تهران", execution_location: "محدوده شهری", notice_number: "INQ-501", source_label: "پارس نماد داده", source_count: 1,
    published_date: "2026-07-22T09:00:00+03:30", last_seen_at: "2026-07-22T17:10:00+03:30", submission_deadline: "2026-07-23T13:00:00+03:30", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب",
    recommendation_score: 88, recommendation_reason: "قابل پاسخ سریع و مرتبط با خدمات پایه مشاوره.", analysis_risk: "کمتر از ۲۴ ساعت تا پایان مهلت باقی مانده است.", suggested_action: "دریافت قیمت تیم نقشه‌برداری و ارسال پاسخ امروز.", responsible_username: "کارشناس مناقصات", next_action: "دریافت قیمت و تأیید مدیر", next_action_due: "2026-07-23T09:00:00+03:30", internal_deadline: "2026-07-23T11:00:00+03:30", preparation_status: "در انتظار تأیید قیمت", progress: 70,
    summary: "برداشت وضع موجود و تهیه نقشه پایه برای پروژه شهری.", description: "استعلام کوتاه‌مدت با امکان پاسخ سریع.", conditions: "ارائه قیمت، زمان انجام و معرفی تیم.", estimated_amount_label: "نیازمند اعلام قیمت", guarantee_label: "ندارد", analysis_summary: "فرصت مناسب ولی بسیار فوری است و باید امروز تصمیم‌گیری شود.",
  },
  {
    ...sharedNoticeDefaults,
    id: "I-002", title: "استعلام تهیه گزارش توجیهی و امکان‌سنجی", employer_name: "منطقه ویژه اقتصادی", province: "بوشهر", city: "عسلویه", execution_location: "منطقه ویژه", notice_number: "INQ-774", source_label: "هزاره", source_count: 1,
    published_date: "2026-07-21T11:00:00+03:30", last_seen_at: "2026-07-22T17:12:00+03:30", submission_deadline: "2026-07-26T15:00:00+03:30", processing_status_label: "تحلیل‌شده", is_recommended: true, case_stage_label: "منتخب",
    recommendation_score: 86, recommendation_reason: "مرتبط با مطالعات امکان‌سنجی و ارزیابی سرمایه‌گذاری.", analysis_risk: "نیازمند ورودی مالی از واحد اقتصادی است.", suggested_action: "تکمیل فرضیات مالی و اخذ تأیید مبلغ پیشنهادی.", responsible_username: "واحد مطالعات", next_action: "جلسه با کارشناس مالی", next_action_due: "2026-07-24T09:30:00+03:30", internal_deadline: "2026-07-25T12:00:00+03:30", preparation_status: "در حال تهیه پیشنهاد مالی", progress: 48,
    summary: "تهیه گزارش توجیهی فنی و اقتصادی یک طرح سرمایه‌گذاری.", description: "استعلام شامل خدمات فنی، مالی و تحلیل حساسیت است.", conditions: "سوابق امکان‌سنجی و معرفی تیم اقتصادی.", estimated_amount_label: "در حال برآورد", guarantee_label: "ندارد", analysis_summary: "فرصت مناسب با نیاز جدی به هماهنگی واحد مالی.",
  },
  {
    ...sharedNoticeDefaults,
    id: "I-003", title: "استعلام طراحی روشنایی محوطه صنعتی", employer_name: "شرکت تولیدی نمونه", province: "قزوین", city: "آبیک", execution_location: "کارخانه", notice_number: "INQ-881", source_label: "پارس نماد داده", source_count: 1,
    published_date: "2026-07-22T10:10:00+03:30", last_seen_at: "2026-07-22T17:10:00+03:30", submission_deadline: "2026-07-24T10:00:00+03:30", processing_status_label: "در انتظار تحلیل", is_recommended: false, case_stage_label: null,
    recommendation_score: 0, recommendation_reason: "هنوز تحلیل نشده است.", analysis_risk: "جزئیات توان و محدوده روشنایی ناقص است.", suggested_action: "دریافت پیوست فنی و اجرای تحلیل.", summary: "طراحی روشنایی محوطه صنعتی.", description: "در انتظار دریافت اطلاعات کامل.", conditions: "نامشخص", estimated_amount_label: "نامشخص", guarantee_label: "ندارد", analysis_summary: "در انتظار تحلیل.",
  },
  {
    ...sharedNoticeDefaults,
    id: "I-004", title: "استعلام بازنگری نقشه‌های معماری", employer_name: "شرکت عمران و مسکن", province: "مازندران", city: "ساری", execution_location: "ساری", notice_number: "INQ-411", source_label: "هزاره", source_count: 1,
    published_date: "2026-07-10T09:00:00+03:30", last_seen_at: "2026-07-20T17:00:00+03:30", submission_deadline: "2026-07-18T12:00:00+03:30", processing_status_label: "نتیجه ثبت‌شده", is_recommended: true, case_stage_label: "نتایج", result_label: "ناموفق",
    recommendation_score: 79, recommendation_reason: "مرتبط با خدمات معماری و قابل انجام در زمان کوتاه.", analysis_risk: "رقابت قیمتی زیاد بود.", suggested_action: "ثبت علت باخت و اصلاح الگوی قیمت‌گذاری.", responsible_username: "واحد فنی", next_action: "جلسه مرور نتیجه", next_action_due: "2026-07-25T10:00:00+03:30", preparation_status: "نتیجه نهایی", progress: 100,
    submission_info: { sent_at: "2026-07-17T11:30:00+03:30", method: "ایمیل", tracking_code: "MAIL-771", recipient: "واحد تدارکات", proposed_amount: "۴.۸ میلیارد ریال", result_followup_at: null },
    summary: "بازنگری محدود نقشه‌های معماری یک مجموعه مسکونی.", description: "نتیجه ناموفق ثبت شده است.", conditions: "ارائه قیمت و برنامه زمانی کوتاه.", estimated_amount_label: "۴.۸ میلیارد ریال", guarantee_label: "ندارد", analysis_summary: "علت اصلی باخت، قیمت بالاتر از رقیب گزارش شده است.", documents: ["استعلام", "پیشنهاد قیمت", "ایمیل ارسال", "اعلام نتیجه"], missing_information: [],
  },
];

const seedOpportunities: DirectOpportunity[] = [
  { id: "D-001", title: "رایزنی طرح توسعه پردیس اداری", employer_name: "گروه سرمایه‌گذاری پارس", stage_label: "در حال مذاکره", next_action: "ارسال معرفی‌نامه سوابق", next_action_due: "2026-07-23T11:00:00+03:30", opportunity_type: "دعوت مستقیم", responsible_username: "محمد ملکی", last_activity_at: "2026-07-22T09:00:00+03:30", probability: 70, risk_label: "متوسط", description: "فرصت مستقیم برای طراحی و مدیریت طرح توسعه پردیس اداری.", documents: ["یادداشت جلسه اولیه"], notes: ["کارفرما رزومه پروژه‌های اداری را درخواست کرده است."] },
  { id: "D-002", title: "مطالعات امکان‌سنجی نیروگاه خورشیدی", employer_name: "شرکت انرژی نو", stage_label: "در حال پیگیری", next_action: "هماهنگی جلسه فنی", next_action_due: "2026-07-25T10:00:00+03:30", opportunity_type: "معرفی شریک تجاری", responsible_username: "واحد توسعه کسب‌وکار", last_activity_at: "2026-07-21T16:00:00+03:30", probability: 55, risk_label: "زیاد", description: "بررسی امکان‌سنجی فنی و اقتصادی نیروگاه خورشیدی.", documents: [], notes: ["دامنه دقیق خدمات هنوز قطعی نشده است."] },
  { id: "D-003", title: "دعوت محدود طراحی مجموعه درمانی", employer_name: "بنیاد توسعه سلامت", stage_label: "پیشنهاد ارسال‌شده", next_action: "پیگیری دریافت پیشنهاد", next_action_due: "2026-07-24T09:00:00+03:30", opportunity_type: "دعوت محدود", responsible_username: "مدیر فنی", last_activity_at: "2026-07-22T12:30:00+03:30", probability: 80, risk_label: "کم", description: "دعوت مستقیم برای طراحی معماری و تأسیسات یک مجموعه درمانی.", documents: ["دعوت‌نامه", "پیشنهاد اولیه"], notes: ["پیشنهاد اولیه ارسال شده است."] },
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

function safeDeadline(value: string | null) {
  if (!value) return null;
  return new Date(value.length === 10 ? `${value}T23:59:59` : value);
}

function displayDate(value: string | null | undefined) {
  const date = value ? safeDeadline(value) : null;
  return date && !Number.isNaN(date.getTime()) ? faDate.format(date) : "تعیین نشده";
}

function displayDateTime(value: string | null | undefined) {
  const date = value ? safeDeadline(value) : null;
  return date && !Number.isNaN(date.getTime()) ? faDateTime.format(date) : "تعیین نشده";
}

function urgencyOf(value: string | null): Urgency {
  const date = safeDeadline(value);
  if (!date || Number.isNaN(date.getTime())) return { label: "تاریخ نامشخص", remaining: "زمان باقی‌مانده نامشخص", tone: "unknown" };
  const hours = Math.ceil((date.getTime() - Date.now()) / 3600000);
  if (hours < 0) return { label: "مهلت گذشته", remaining: `${faNumber.format(Math.abs(hours))} ساعت از مهلت گذشته`, tone: "critical" };
  if (hours < 24) return { label: "فوریت بحرانی", remaining: `${faNumber.format(hours)} ساعت باقی‌مانده`, tone: "critical" };
  if (hours <= 72) return { label: "فوریت زیاد", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "high" };
  if (hours <= 168) return { label: "فوریت متوسط", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "medium" };
  return { label: "فوریت عادی", remaining: `${faNumber.format(Math.ceil(hours / 24))} روز باقی‌مانده`, tone: "normal" };
}

function actionUrgency(value: string | null): Urgency {
  return urgencyOf(value);
}

function urgencyClass(tone: Urgency["tone"]) {
  if (tone === "critical") return styles.critical;
  if (tone === "high") return styles.high;
  if (tone === "medium") return styles.medium;
  if (tone === "normal") return styles.normal;
  return styles.unknown;
}

function normalizeNotice(item: ApiNotice): Notice {
  const sourceNames = item.source_links?.map((link) => link.source_notice?.source_name).filter(Boolean) as string[] | undefined;
  return {
    ...item,
    case_stage_label: item.case_stage_label || item.case?.stage_label || null,
    responsible_username: item.responsible_username || item.case?.responsible_username,
    next_action: item.next_action || item.case?.next_action,
    next_action_due: item.next_action_due || item.case?.next_action_due,
    progress: item.progress ?? item.case?.progress,
    source_label: item.source_label || sourceNames?.join("، ") || (item.source_count ? `${faNumber.format(item.source_count)} منبع` : "منبع ثبت‌شده"),
    estimated_amount_label: item.estimated_amount_label || (item.estimated_amount_rials ? `${item.estimated_amount_rials} ریال` : undefined),
    guarantee_label: item.guarantee_label || (item.guarantee_amount_rials ? `${item.guarantee_amount_rials} ریال` : undefined),
  };
}

function matchesView(item: Notice, view: NoticeView) {
  if (view === "all") return true;
  if (view === "recommended") return item.is_recommended && !item.case_stage_label;
  if (view === "selected") return item.case_stage_label === "منتخب" || item.case_stage_label === "در دست تهیه";
  if (view === "submitted") return item.case_stage_label === "ارسال‌شده";
  return item.case_stage_label === "نتایج" || Boolean(item.result_label);
}

export default function ProcurementPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [noticeView, setNoticeView] = useState<NoticeView>("all");
  const [detailSection, setDetailSection] = useState<DetailSection>("summary");
  const [mode, setMode] = useState<DataMode>("loading");
  const [dashboard, setDashboard] = useState<Dashboard>(seedDashboard);
  const [tenders, setTenders] = useState<Notice[]>(seedTenders);
  const [inquiries, setInquiries] = useState<Notice[]>(seedInquiries);
  const [opportunities, setOpportunities] = useState<DirectOpportunity[]>(seedOpportunities);
  const [sources, setSources] = useState<Source[]>(seedSources);
  const [automation, setAutomation] = useState<AutomationSettings>(seedAutomation);
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>(["C-HT", "C-HI", "C-PT", "C-PI"]);
  const [selectedNotice, setSelectedNotice] = useState<Notice | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<DirectOpportunity | null>(null);
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
        const [dashboardData, tenderData, inquiryData, directData, sourceData, automationData] = await Promise.all(responses.map((response) => response.json()));
        if (cancelled) return;
        const sourceItems = itemsOf<Source>(sourceData);
        setDashboard(dashboardData as Dashboard);
        setTenders(itemsOf<ApiNotice>(tenderData).map(normalizeNotice));
        setInquiries(itemsOf<ApiNotice>(inquiryData).map(normalizeNotice));
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

  const allNotices = useMemo(() => [...tenders, ...inquiries], [inquiries, tenders]);
  const displayedNotices = useMemo(() => {
    const base = tab === "tenders" ? tenders : inquiries;
    return base.filter((item) => matchesView(item, noticeView) && (!search || `${item.title} ${item.employer_name} ${item.province} ${item.source_label || ""}`.includes(search)));
  }, [inquiries, noticeView, search, tab, tenders]);

  const managementCounts = useMemo(() => {
    const selected = allNotices.filter((item) => matchesView(item, "selected")).length;
    const submitted = allNotices.filter((item) => matchesView(item, "submitted")).length;
    const pendingAnalysis = allNotices.filter((item) => item.processing_status_label.includes("انتظار تحلیل")).length;
    const urgent = allNotices.filter((item) => ["critical", "high"].includes(urgencyOf(item.submission_deadline).tone) && !item.result_label).length;
    const wins = allNotices.filter((item) => item.result_label === "برنده").length;
    const losses = allNotices.filter((item) => item.result_label === "ناموفق").length;
    return { selected, submitted, pendingAnalysis, urgent, wins, losses };
  }, [allNotices]);

  const activeCases = useMemo(() => allNotices.filter((item) => matchesView(item, "selected") || matchesView(item, "submitted")).slice(0, 6), [allNotices]);
  const overdueOpportunityCount = useMemo(() => opportunities.filter((item) => actionUrgency(item.next_action_due).tone === "critical").length, [opportunities]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 4200);
  }

  function updateNotice(id: string, updater: (item: Notice) => Notice) {
    setTenders((items) => items.map((item) => item.id === id ? updater(item) : item));
    setInquiries((items) => items.map((item) => item.id === id ? updater(item) : item));
    setSelectedNotice((item) => item?.id === id ? updater(item) : item);
  }

  function previewOnlyAction() {
    if (mode === "demo") return true;
    notify("این عملیات در این مرحله فقط در Preview نمایشی فعال است و پس از تأیید به API عملیاتی متصل می‌شود.");
    return false;
  }

  async function openNotice(item: Notice) {
    setSelectedNotice(item);
    setDetailSection("summary");
    if (mode !== "live") return;
    try {
      const response = await fetch(`${API_BASE}/procurement/notices/${item.id}/`, { credentials: "include" });
      if (response.ok) setSelectedNotice(normalizeNotice(await response.json() as ApiNotice));
    } catch {
      notify("جزئیات تکمیلی دریافت نشد؛ اطلاعات فهرست نمایش داده می‌شود.");
    }
  }

  function selectForParticipation(item: Notice) {
    if (!previewOnlyAction()) return;
    updateNotice(item.id, (current) => ({
      ...current,
      is_recommended: true,
      case_stage_label: "منتخب",
      processing_status_label: "منتخب برای بررسی",
      responsible_username: current.responsible_username || "محمد ملکی",
      next_action: "تعیین مسئول و برنامه تهیه پیشنهاد",
      next_action_due: new Date(Date.now() + 86400000).toISOString(),
      preparation_status: "انتخاب‌شده",
      progress: 5,
    }));
    notify("رکورد به فهرست منتخب منتقل شد.");
  }

  function dismissRecommendation(item: Notice) {
    if (!previewOnlyAction()) return;
    const reason = window.prompt("دلیل حذف از پیشنهادها را ثبت کنید:", "تصمیم مدیریت");
    if (!reason) return;
    updateNotice(item.id, (current) => ({ ...current, is_recommended: false, processing_status_label: `حذف از پیشنهادها: ${reason}` }));
    notify("رکورد از پیشنهادها حذف شد؛ اطلاعات اصلی و تاریخچه باقی ماند.");
  }

  function removeSelected(item: Notice) {
    if (!previewOnlyAction()) return;
    const reason = window.prompt("دلیل حذف از منتخب‌ها را ثبت کنید:", "تغییر تصمیم شرکت");
    if (!reason) return;
    const returnToRecommended = window.confirm("برای بازگشت رکورد به فهرست پیشنهادی «تأیید» را بزنید؛ برای خروج از فرایند «لغو» را انتخاب کنید.");
    updateNotice(item.id, (current) => ({
      ...current,
      is_recommended: returnToRecommended,
      case_stage_label: null,
      preparation_status: undefined,
      progress: 0,
      processing_status_label: returnToRecommended ? `بازگشت به پیشنهادی: ${reason}` : `خروج از فرایند: ${reason}`,
    }));
    notify(returnToRecommended ? "رکورد به پیشنهادها بازگشت." : "رکورد از فرایند خارج شد؛ سابقه حذف نشده است.");
  }

  function addFollowUp(item: Notice) {
    if (!previewOnlyAction()) return;
    const action = window.prompt("اقدام بعدی را ثبت کنید:", item.next_action || "پیگیری با کارفرما");
    if (!action) return;
    updateNotice(item.id, (current) => ({ ...current, next_action: action, next_action_due: new Date(Date.now() + 86400000).toISOString() }));
    notify("اقدام بعدی در Preview ثبت شد.");
  }

  function updateProgress(item: Notice) {
    if (!previewOnlyAction()) return;
    const value = window.prompt("درصد پیشرفت آماده‌سازی را وارد کنید:", String(item.progress || 0));
    if (value === null) return;
    const progress = Math.max(0, Math.min(100, Number(value) || 0));
    const statuses = progress >= 90 ? "آماده ارسال" : progress >= 60 ? "در حال تهیه پیشنهاد مالی" : progress >= 30 ? "در حال تهیه پیشنهاد فنی" : "در حال جمع‌آوری اسناد";
    updateNotice(item.id, (current) => ({ ...current, progress, preparation_status: statuses }));
    notify("پیشرفت آماده‌سازی به‌روزرسانی شد.");
  }

  function markSubmitted(item: Notice) {
    if (!previewOnlyAction()) return;
    const tracking = window.prompt("شماره رهگیری یا رسید ارسال را وارد کنید:", "PREVIEW-TRACK");
    if (!tracking) return;
    updateNotice(item.id, (current) => ({
      ...current,
      case_stage_label: "ارسال‌شده",
      processing_status_label: "ارسال‌شده",
      preparation_status: "ارسال تکمیل شده",
      progress: 100,
      submission_info: { sent_at: new Date().toISOString(), method: "سامانه کارفرما", tracking_code: tracking, recipient: "دبیرخانه کارفرما", result_followup_at: new Date(Date.now() + 3 * 86400000).toISOString() },
      documents: [...(current.documents || []), "رسید ارسال"],
    }));
    notify("رکورد به ارسال‌شده منتقل شد.");
  }

  function registerResult(item: Notice) {
    if (!previewOnlyAction()) return;
    const result = window.prompt("نتیجه را وارد کنید: برنده، ناموفق، لغوشده یا بی‌نتیجه", item.result_label || "برنده");
    if (!result) return;
    updateNotice(item.id, (current) => ({ ...current, case_stage_label: "نتایج", result_label: result, processing_status_label: "نتیجه ثبت‌شده" }));
    notify("نتیجه در Preview ثبت شد.");
  }

  function addDocument(item: Notice) {
    if (!previewOnlyAction()) return;
    const documentName = window.prompt("عنوان سند را وارد کنید:", "رسید یا مدرک جدید");
    if (!documentName) return;
    updateNotice(item.id, (current) => ({ ...current, documents: [...(current.documents || []), documentName] }));
    notify("سند به پرونده نمایشی افزوده شد.");
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
      window.setTimeout(() => { setBusy(false); notify("استخراج نمایشی پایان یافت: ۲۴ رکورد جدید و ۳ رکورد به‌روزرسانی‌شده."); }, 900);
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
        opportunity_type: "نیازمند تعیین",
        responsible_username: "ثبت‌کننده",
        last_activity_at: new Date().toISOString(),
        probability: 20,
        risk_label: "نیازمند بررسی",
        description: "فرصت جدید ثبت‌شده در Preview.",
        documents: [],
        notes: [],
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

  function updateDirectOpportunity(id: string, updater: (item: DirectOpportunity) => DirectOpportunity) {
    setOpportunities((items) => items.map((item) => item.id === id ? updater(item) : item));
    setSelectedOpportunity((item) => item?.id === id ? updater(item) : item);
  }

  function followUpOpportunity(item: DirectOpportunity) {
    if (!previewOnlyAction()) return;
    const action = window.prompt("اقدام بعدی فرصت را وارد کنید:", item.next_action);
    if (!action) return;
    updateDirectOpportunity(item.id, (current) => ({ ...current, next_action: action, next_action_due: new Date(Date.now() + 86400000).toISOString(), last_activity_at: new Date().toISOString() }));
    notify("پیگیری فرصت در Preview ثبت شد.");
  }

  function changeOpportunityStage(item: DirectOpportunity) {
    if (!previewOnlyAction()) return;
    const stage = window.prompt("مرحله جدید را وارد کنید:", item.stage_label);
    if (!stage) return;
    updateDirectOpportunity(item.id, (current) => ({ ...current, stage_label: stage, last_activity_at: new Date().toISOString() }));
    notify("مرحله فرصت تغییر کرد.");
  }

  function removeOpportunity(item: DirectOpportunity) {
    if (!previewOnlyAction()) return;
    const reason = window.prompt("دلیل حذف از فهرست را ثبت کنید:", "تصمیم مدیریت");
    if (!reason) return;
    setOpportunities((items) => items.filter((current) => current.id !== item.id));
    setSelectedOpportunity(null);
    notify(`فرصت به‌صورت Soft Delete از فهرست Preview خارج شد: ${reason}`);
  }

  const tabs: [Tab, string][] = [
    ["dashboard", "داشبورد مدیریتی"], ["tenders", "مناقصات"], ["inquiries", "استعلامات"],
    ["direct", "فرصت‌های خارج از سامانه"], ["management", "مدیریت زیرسامانه"],
  ];
  const views: [NoticeView, string][] = [
    ["all", "همه"], ["recommended", "پیشنهادی"], ["selected", "منتخب"], ["submitted", "ارسال‌شده"], ["results", "نتایج"],
  ];
  const detailSections: [DetailSection, string][] = [
    ["summary", "خلاصه"], ["followup", "پیگیری و اقدام"], ["documents", "اسناد"], ["more", "اطلاعات بیشتر"],
  ];

  return <main className={styles.page} dir="rtl">
    <header className={styles.header}>
      <div><span>زیرسامانه تخصصی PDP One</span><h1>فرصت‌ها و مناقصات</h1><p>استخراج، تحلیل ChatGPT، پیگیری و تصمیم‌سازی در یک مسیر کنترل‌شده</p></div>
      <div className={styles.headerActions}><a href="/">بازگشت به سامانه</a></div>
    </header>

    {mode !== "live" && <div className={styles.demoBanner}><b>{mode === "loading" ? "در حال بررسی اتصال..." : "حالت Preview تعاملی"}</b><span>{mode === "demo" ? "داده‌ها نمونه‌اند و هیچ تغییری در سامانه واقعی ایجاد نمی‌شود." : "در صورت نبود Backend، داده نمونه بارگذاری می‌شود."}</span></div>}

    <nav className={styles.tabs}>{tabs.map(([id, label]) => <button key={id} className={tab === id ? styles.active : ""} onClick={() => { setTab(id); setNoticeView("all"); setSearch(""); }}>{label}</button>)}</nav>

    {message && <div className={styles.message}>{message}</div>}

    {tab === "dashboard" && <section>
      <div className={styles.kpisWide}>
        <article><span>فراخوان جدید</span><b>{faNumber.format(24)}</b><small>از آخرین استخراج</small></article>
        <article><span>تحلیل‌نشده</span><b>{faNumber.format(managementCounts.pendingAnalysis)}</b><small>در انتظار اجرای ChatGPT</small></article>
        <article><span>پیشنهادی</span><b>{faNumber.format(allNotices.filter((item) => matchesView(item, "recommended")).length)}</b><small>نیازمند تصمیم انسانی</small></article>
        <article><span>منتخب</span><b>{faNumber.format(managementCounts.selected)}</b><small>پرونده در جریان</small></article>
        <article><span>ارسال‌شده</span><b>{faNumber.format(managementCounts.submitted)}</b><small>در انتظار نتیجه</small></article>
        <article><span>نزدیک مهلت</span><b>{faNumber.format(managementCounts.urgent)}</b><small>نیازمند اقدام فوری</small></article>
        <article><span>فرصت مستقیم فعال</span><b>{faNumber.format(opportunities.length)}</b><small>{faNumber.format(overdueOpportunityCount)} پیگیری عقب‌افتاده</small></article>
        <article><span>نتیجه موفق</span><b>{faNumber.format(managementCounts.wins)}</b><small>{faNumber.format(managementCounts.losses)} نتیجه ناموفق</small></article>
      </div>

      <div className={styles.dashboardGrid}>
        <article className={`${styles.panel} ${styles.widePanel}`}><div className={styles.panelTitle}><div><span>پرونده‌های فعال</span><h2>اقدامات نیازمند توجه مدیریت</h2></div><small>منتخب و ارسال‌شده</small></div><div className={styles.caseTable}>
          {activeCases.map((item) => { const urgency = urgencyOf(item.submission_deadline); return <button key={item.id} onClick={() => openNotice(item)}><span><b>{item.title}</b><small>{item.employer_name} · {item.responsible_username || "بدون مسئول"}</small></span><span><b>{item.preparation_status || item.case_stage_label}</b><small>{item.next_action || "اقدام بعدی ثبت نشده"}</small></span><span className={`${styles.urgency} ${urgencyClass(urgency.tone)}`}><b>{urgency.label}</b><small>{urgency.remaining}</small></span></button>; })}
        </div></article>

        <article className={styles.panel}><h2>هشدارهای مدیریتی</h2><div className={styles.alertList}><span>۳ اقدام پیگیری عقب‌افتاده</span><span>۲ پرونده بدون مسئول</span><span>{faNumber.format(managementCounts.urgent)} فراخوان نزدیک به مهلت</span><span>۱ پرونده ارسال‌شده بدون پیگیری نتیجه</span><span>۲ پرونده دارای نقص اسناد</span></div></article>
        <article className={styles.panel}><h2>قیف مدیریتی</h2><div className={styles.funnel}><span>استخراج‌شده {faNumber.format(dashboard.notices.total)}</span><span>پیشنهادی {faNumber.format(dashboard.notices.recommended)}</span><span>منتخب {faNumber.format(managementCounts.selected)}</span><span>ارسال‌شده {faNumber.format(managementCounts.submitted)}</span><span>برنده {faNumber.format(managementCounts.wins)}</span></div></article>
        <article className={styles.panel}><h2>برد و باخت</h2><div className={styles.outcomeGrid}><div><b>{faNumber.format(managementCounts.wins)}</b><span>برنده</span></div><div><b>{faNumber.format(managementCounts.losses)}</b><span>ناموفق</span></div><div><b>۵۰٪</b><span>نرخ برد نمونه</span></div><div><b>۶۲</b><span>میلیارد ریال حاصل</span></div></div><small>دلایل پرتکرار باخت: قیمت، زمان محدود و نقص مستندات.</small></article>
        <article className={styles.panel}><h2>جمع‌بندی مدیریتی ChatGPT</h2><p>فرصت «طرح جامع و برنامه‌ریزی فضایی فارس» بالاترین تناسب را دارد. استعلام نقشه‌برداری تهران کمتر از ۲۴ ساعت زمان دارد و نیازمند تصمیم فوری است. پرونده شهرک صنعتی ارسال شده ولی پیگیری نتیجه آن باید ثبت شود.</p><div className={styles.summaryTags}><span>اولویت امروز: استعلام تهران</span><span>ریسک اصلی: مهلت محدود</span><span>فرصت راهبردی: طرح جامع فارس</span></div></article>
      </div>
    </section>}

    {(tab === "tenders" || tab === "inquiries") && <section>
      <div className={styles.sectionHeading}><div><span>{tab === "tenders" ? "فرآیند مناقصات" : "فرآیند استعلامات"}</span><h2>{tab === "tenders" ? "مناقصات" : "استعلامات"}</h2></div><small>مهلت، زمان باقی‌مانده، فوریت، وضعیت تحلیل و اقدام بعدی مستقیماً در فهرست نمایش داده می‌شوند.</small></div>
      <div className={styles.viewTabs}>{views.map(([id, label]) => <button key={id} className={noticeView === id ? styles.selectedView : ""} onClick={() => setNoticeView(id)}>{label}</button>)}</div>
      <div className={styles.toolbar}><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="عنوان، کارفرما، استان یا منبع..." /><span>{faNumber.format(displayedNotices.length)} رکورد</span></div>
      <div className={styles.noticeList}>{displayedNotices.map((item) => {
        const urgency = urgencyOf(item.submission_deadline);
        return <article key={item.id} className={styles.noticeCard}>
          <div className={styles.noticeMain}><div className={styles.noticeTopline}><small>{item.source_label || "منبع نامشخص"} · {item.province || "استان نامشخص"} · {item.processing_status_label}</small><span className={`${styles.urgencyPill} ${urgencyClass(urgency.tone)}`}>{urgency.label}</span></div><h3>{item.title}</h3><p>{item.employer_name || "کارفرما ثبت نشده"}</p><div className={styles.noticeFacts}><span>انتشار: {displayDate(item.published_date)}</span><span>مهلت: {displayDateTime(item.submission_deadline)}</span><span>{urgency.remaining}</span><span>آخرین به‌روزرسانی: {displayDateTime(item.last_seen_at)}</span></div>{item.missing_information?.length ? <div className={styles.missingInfo}>نقص اطلاعات: {item.missing_information.join("، ")}</div> : null}</div>
          <div className={styles.noticeDecision}><span className={styles.stageBadge}>{item.result_label || item.preparation_status || item.case_stage_label || (item.is_recommended ? "پیشنهادی" : "در انتظار تحلیل")}</span><dl><div><dt>اولویت تحلیلی</dt><dd>{item.recommendation_score ? `${faNumber.format(item.recommendation_score)} از ۱۰۰` : "تحلیل نشده"}</dd></div><div><dt>مسئول</dt><dd>{item.responsible_username || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{item.next_action || item.suggested_action || "تعیین نشده"}</dd></div></dl><div className={styles.noticeActions}>
            <button onClick={() => openNotice(item)}>مشاهده</button>
            {noticeView === "recommended" && <><button className={styles.primaryAction} onClick={() => selectForParticipation(item)}>انتخاب</button><button className={styles.dangerAction} onClick={() => dismissRecommendation(item)}>حذف</button><button onClick={() => addFollowUp(item)}>پیگیری</button></>}
            {noticeView === "selected" && <><button onClick={() => addFollowUp(item)}>پیگیری</button><button onClick={() => updateProgress(item)}>ثبت پیشرفت</button><button className={styles.primaryAction} onClick={() => markSubmitted(item)}>ارسال شد</button><button className={styles.dangerAction} onClick={() => removeSelected(item)}>حذف</button></>}
            {noticeView === "submitted" && <><button className={styles.primaryAction} onClick={() => registerResult(item)}>ثبت نتیجه</button><button onClick={() => addFollowUp(item)}>ثبت پیگیری</button><button onClick={() => addDocument(item)}>افزودن سند</button></>}
            {noticeView === "results" && <><button onClick={() => registerResult(item)}>اصلاح نتیجه</button><button onClick={() => notify(item.result_label === "برنده" ? "تبدیل به قرارداد پس از تأیید مدیر انجام می‌شود." : "فقط پرونده برنده قابل تبدیل به قرارداد است.")}>تبدیل به قرارداد</button><button onClick={() => notify("پرونده در Preview بسته شد؛ تاریخچه باقی می‌ماند.")}>بستن پرونده</button></>}
          </div></div>
        </article>;
      })}{!displayedNotices.length && <div className={styles.empty}>رکوردی مطابق این نما و جست‌وجو وجود ندارد.</div>}</div>
    </section>}

    {tab === "direct" && <section>
      <div className={styles.sectionHeading}><div><span>ثبت و پیگیری سریع</span><h2>فرصت‌های خارج از سامانه</h2></div><small>ثبت اولیه سه‌فیلدی است؛ فوریت پیگیری، احتمال تبدیل، ریسک و مسئول در فهرست دیده می‌شوند.</small></div>
      <div className={styles.directKpis}><article><span>فرصت جدید</span><b>{faNumber.format(opportunities.filter((item) => item.stage_label === "فرصت جدید").length)}</b></article><article><span>پیگیری امروز یا معوق</span><b>{faNumber.format(overdueOpportunityCount)}</b></article><article><span>در حال مذاکره</span><b>{faNumber.format(opportunities.filter((item) => item.stage_label.includes("مذاکره") || item.stage_label.includes("پیگیری")).length)}</b></article><article><span>پیشنهاد ارسال‌شده</span><b>{faNumber.format(opportunities.filter((item) => item.stage_label.includes("ارسال")).length)}</b></article></div>
      <div className={styles.grid}>
        <article className={styles.panel}><h2>ثبت سریع فرصت</h2><form className={styles.form} onSubmit={createDirectOpportunity}><label>عنوان فرصت<input name="title" required /></label><label>کارفرما<input name="employer_name" required /></label><label>اقدام بعدی<input name="next_action" required /></label><button disabled={busy}>ثبت فرصت</button></form><small>نوع «نیازمند تعیین»، مسئول «ثبت‌کننده» و پیگیری بعدی «فردا» به‌صورت پیش‌فرض ثبت می‌شوند.</small></article>
        <article className={`${styles.panel} ${styles.opportunityPanel}`}><h2>فرصت‌های در جریان</h2><div className={styles.opportunityList}>{opportunities.map((item) => { const urgency = actionUrgency(item.next_action_due); return <article key={item.id}><div><small>{item.opportunity_type || "نوع نامشخص"} · {item.stage_label}</small><h3>{item.title}</h3><p>{item.employer_name}</p><span>مسئول: {item.responsible_username || "تعیین نشده"} · احتمال تبدیل: {faNumber.format(item.probability || 0)}٪ · ریسک: {item.risk_label || "نامشخص"}</span></div><div className={styles.opportunityMeta}><span className={`${styles.urgencyPill} ${urgencyClass(urgency.tone)}`}>{urgency.remaining}</span><b>{item.next_action}</b><small>{displayDateTime(item.next_action_due)}</small><div><button onClick={() => { setSelectedOpportunity(item); setDetailSection("summary"); }}>مشاهده</button><button onClick={() => followUpOpportunity(item)}>پیگیری</button><button onClick={() => changeOpportunityStage(item)}>تغییر مرحله</button><button className={styles.dangerAction} onClick={() => removeOpportunity(item)}>حذف</button></div></div></article>; })}</div></article>
      </div>
    </section>}

    {tab === "management" && <section>
      <div className={styles.sectionHeading}><div><span>کنترل منابع، استخراج و تحلیل</span><h2>مدیریت زیرسامانه</h2></div><small>عملیات فنی استخراج فقط در این بخش قرار دارد.</small></div>
      <div className={styles.managementGrid}>
        <article className={styles.panel}><h2>منابع استخراج</h2><div className={styles.sourceList}>{sources.map((source) => <div key={source.id}><label><input type="checkbox" checked={source.enabled} disabled={busy} onChange={() => toggleSource(source)} /><b>{source.name}</b></label><span>{source.status_label}</span><small>{source.connectors.map((connector) => `${connector.notice_type_label}: ${connector.enabled ? "فعال" : "غیرفعال"}`).join(" · ")}</small></div>)}</div></article>
        <article className={styles.panel}><h2>اجرای استخراج</h2><div className={styles.connectorList}>{sources.flatMap((source) => source.connectors).map((connector) => <label key={connector.id}><input type="checkbox" checked={selectedConnectors.includes(connector.id)} disabled={!connector.enabled || busy} onChange={(event) => setSelectedConnectors((items) => event.target.checked ? [...new Set([...items, connector.id])] : items.filter((id) => id !== connector.id))} /><span>{connector.key}</span><small>{connector.status_label}</small></label>)}</div><button className={styles.fullButton} disabled={busy} onClick={startExtraction}>{busy ? "در حال اجرا..." : "شروع استخراج منابع انتخاب‌شده"}</button><div className={styles.lastRun}><span>آخرین اجرای نمونه</span><b>موفق با ۳ هشدار</b><small>۲۴ رکورد جدید · ۳ رکورد تغییرکرده · ۱ صفحه جزئیات مسدود</small></div></article>
        <article className={styles.panel}><h2>زمان‌بندی استخراج</h2><dl><div><dt>وضعیت</dt><dd>{automation.enabled ? "فعال" : "غیرفعال تا تأیید Preview"}</dd></div><div><dt>نوع برنامه</dt><dd>{automation.cadence_label}</dd></div><div><dt>ساعت روزانه</dt><dd>{automation.daily_time || "تعیین نشده"}</dd></div><div><dt>تأخیر تحلیل ChatGPT</dt><dd>{automation.analysis_delay_minutes} دقیقه</dd></div><div><dt>اجرای بعدی</dt><dd>{displayDateTime(automation.next_extraction_at)}</dd></div></dl></article>
        <article className={styles.panel}><h2>تنظیمات تحلیل هوشمند</h2><dl><div><dt>موتور تحلیل</dt><dd>ChatGPT + MCP</dd></div><div><dt>OpenAI API پولی</dt><dd>استفاده نمی‌شود</dd></div><div><dt>فرمان دستی</dt><dd>{automation.manual_command}</dd></div><div><dt>ثبت خروجی</dt><dd>Draft-first</dd></div><div><dt>اجرای Scheduled Task</dt><dd>نیازمند آزمون Preview</dd></div></dl></article>
        <article className={styles.panel}><h2>نسخه‌های زمینه تحلیل</h2><dl><div><dt>Context Snapshot</dt><dd>نسخه ۱۲</dd></div><div><dt>Prompt تحلیل</dt><dd>نسخه ۵</dd></div><div><dt>کلیدواژه‌ها</dt><dd>نسخه ۸</dd></div><div><dt>پروفایل شرکت</dt><dd>نسخه ۳</dd></div><div><dt>صلاحیت‌ها</dt><dd>نسخه ۴</dd></div></dl></article>
        <article className={styles.panel}><h2>نگهداری و کنترل</h2><div className={styles.alertList}><span>رکوردهای منتخب و ارسال‌شده از پاک‌سازی محافظت می‌شوند.</span><span>حذف‌های کاربری Soft Delete و Audit‌شده هستند.</span><span>ستاد ایران موقتاً تعلیق‌شده و نیازمند بررسی مجدد در ساعت دسترسی است.</span><span>هیچ داده، فایل خصوصی یا Secret در Preview قرار نگرفته است.</span></div></article>
      </div>
    </section>}

    {selectedNotice && <div className={styles.modalBackdrop} role="presentation" onMouseDown={() => setSelectedNotice(null)}><section className={styles.detailModal} role="dialog" aria-modal="true" aria-label="جزئیات فراخوان" onMouseDown={(event) => event.stopPropagation()}>
      <header className={styles.detailHeader}><div><small>{selectedNotice.source_label} · {selectedNotice.notice_number || "کد نامشخص"}</small><h2>{selectedNotice.title}</h2><p>{selectedNotice.employer_name} · {selectedNotice.province}</p></div><button onClick={() => setSelectedNotice(null)} aria-label="بستن">×</button></header>
      <nav className={styles.detailTabs}>{detailSections.map(([id, label]) => <button key={id} className={detailSection === id ? styles.selectedDetail : ""} onClick={() => setDetailSection(id)}>{label}</button>)}</nav>
      <div className={styles.detailBody}>
        {detailSection === "summary" && (() => { const urgency = urgencyOf(selectedNotice.submission_deadline); return <><div className={styles.detailKpis}><article><span>مهلت ارسال</span><b>{displayDateTime(selectedNotice.submission_deadline)}</b><small>{urgency.remaining}</small></article><article><span>سطح فوریت</span><b className={urgencyClass(urgency.tone)}>{urgency.label}</b><small>بر مبنای زمان باقی‌مانده</small></article><article><span>اولویت تحلیلی</span><b>{selectedNotice.recommendation_score ? `${faNumber.format(selectedNotice.recommendation_score)} / ۱۰۰` : "تحلیل نشده"}</b><small>{selectedNotice.confidence_label || "نامشخص"}</small></article><article><span>وضعیت پرونده</span><b>{selectedNotice.result_label || selectedNotice.preparation_status || selectedNotice.case_stage_label || (selectedNotice.is_recommended ? "پیشنهادی" : "ثبت‌شده")}</b><small>{selectedNotice.processing_status_label}</small></article></div><div className={styles.detailColumns}><article><h3>اطلاعات فراخوان</h3><dl><div><dt>کارفرما</dt><dd>{selectedNotice.employer_name}</dd></div><div><dt>محل اجرا</dt><dd>{selectedNotice.execution_location || selectedNotice.city || selectedNotice.province}</dd></div><div><dt>تاریخ انتشار</dt><dd>{displayDateTime(selectedNotice.published_date)}</dd></div><div><dt>آخرین به‌روزرسانی</dt><dd>{displayDateTime(selectedNotice.last_seen_at)}</dd></div><div><dt>منبع</dt><dd>{selectedNotice.source_label}</dd></div></dl></article><article><h3>جمع‌بندی تحلیل</h3><p><b>دلیل پیشنهاد:</b> {selectedNotice.recommendation_reason || "ثبت نشده"}</p><p><b>ریسک اصلی:</b> {selectedNotice.analysis_risk || "ثبت نشده"}</p><p><b>اقدام پیشنهادی:</b> {selectedNotice.suggested_action || "ثبت نشده"}</p><p><b>جمع‌بندی:</b> {selectedNotice.analysis_summary || "تحلیل کامل ثبت نشده است."}</p></article></div></>; })()}
        {detailSection === "followup" && <div className={styles.detailColumns}><article><h3>مسئولیت و اقدام</h3><dl><div><dt>مسئول پرونده</dt><dd>{selectedNotice.responsible_username || "تعیین نشده"}</dd></div><div><dt>اقدام بعدی</dt><dd>{selectedNotice.next_action || "ثبت نشده"}</dd></div><div><dt>تاریخ اقدام بعدی</dt><dd>{displayDateTime(selectedNotice.next_action_due)}</dd></div><div><dt>مهلت داخلی</dt><dd>{displayDateTime(selectedNotice.internal_deadline)}</dd></div><div><dt>وضعیت آماده‌سازی</dt><dd>{selectedNotice.preparation_status || "شروع نشده"}</dd></div><div><dt>پیشرفت</dt><dd>{faNumber.format(selectedNotice.progress || 0)}٪</dd></div></dl><div className={styles.progress}><span style={{ width: `${selectedNotice.progress || 0}%` }} /></div></article><article><h3>اطلاعات ارسال و نتیجه</h3><dl><div><dt>تاریخ ارسال</dt><dd>{displayDateTime(selectedNotice.submission_info?.sent_at)}</dd></div><div><dt>روش ارسال</dt><dd>{selectedNotice.submission_info?.method || "ثبت نشده"}</dd></div><div><dt>شماره رهگیری</dt><dd>{selectedNotice.submission_info?.tracking_code || "ثبت نشده"}</dd></div><div><dt>دریافت‌کننده</dt><dd>{selectedNotice.submission_info?.recipient || "ثبت نشده"}</dd></div><div><dt>مبلغ پیشنهادی</dt><dd>{selectedNotice.submission_info?.proposed_amount || "ثبت نشده"}</dd></div><div><dt>نتیجه</dt><dd>{selectedNotice.result_label || "در انتظار"}</dd></div></dl></article></div>}
        {detailSection === "documents" && <div className={styles.detailColumns}><article><h3>اسناد موجود</h3><div className={styles.documentList}>{(selectedNotice.documents || []).map((document) => <button key={document}><span>▤</span><b>{document}</b><small>فایل خصوصی سامانه</small></button>)}{!selectedNotice.documents?.length && <p>سندی ثبت نشده است.</p>}</div></article><article><h3>کنترل نقص اسناد</h3><div className={styles.alertList}>{(selectedNotice.missing_information || []).map((item) => <span key={item}>{item}</span>)}{!selectedNotice.missing_information?.length && <span className={styles.successAlert}>نقص اطلاعات ثبت‌شده‌ای وجود ندارد.</span>}</div><button className={styles.fullButton} onClick={() => addDocument(selectedNotice)}>افزودن سند در Preview</button></article></div>}
        {detailSection === "more" && <div className={styles.detailColumns}><article><h3>شرح و شرایط</h3><p>{selectedNotice.summary || "خلاصه ثبت نشده است."}</p><p>{selectedNotice.description || "شرح کامل ثبت نشده است."}</p><p><b>شرایط:</b> {selectedNotice.conditions || "ثبت نشده"}</p><p><b>صلاحیت موردنیاز:</b> {selectedNotice.qualification_text || "ثبت نشده"}</p></article><article><h3>اطلاعات تکمیلی</h3><dl><div><dt>مبلغ برآورد</dt><dd>{selectedNotice.estimated_amount_label || "نامشخص"}</dd></div><div><dt>تضمین</dt><dd>{selectedNotice.guarantee_label || "نامشخص"}</dd></div><div><dt>تماس</dt><dd>{selectedNotice.contact_text || "ثبت نشده"}</dd></div></dl><h3>سوابق مشابه شرکت</h3><ul>{(selectedNotice.similar_experience || []).map((item) => <li key={item}>{item}</li>)}</ul></article></div>}
      </div>
    </section></div>}

    {selectedOpportunity && <div className={styles.modalBackdrop} role="presentation" onMouseDown={() => setSelectedOpportunity(null)}><section className={styles.detailModal} role="dialog" aria-modal="true" aria-label="جزئیات فرصت مستقیم" onMouseDown={(event) => event.stopPropagation()}>
      <header className={styles.detailHeader}><div><small>{selectedOpportunity.opportunity_type || "فرصت مستقیم"}</small><h2>{selectedOpportunity.title}</h2><p>{selectedOpportunity.employer_name}</p></div><button onClick={() => setSelectedOpportunity(null)} aria-label="بستن">×</button></header>
      <nav className={styles.detailTabs}>{detailSections.map(([id, label]) => <button key={id} className={detailSection === id ? styles.selectedDetail : ""} onClick={() => setDetailSection(id)}>{label}</button>)}</nav>
      <div className={styles.detailBody}>
        {detailSection === "summary" && <div className={styles.detailColumns}><article><h3>خلاصه فرصت</h3><dl><div><dt>مرحله</dt><dd>{selectedOpportunity.stage_label}</dd></div><div><dt>مسئول</dt><dd>{selectedOpportunity.responsible_username || "تعیین نشده"}</dd></div><div><dt>احتمال تبدیل</dt><dd>{faNumber.format(selectedOpportunity.probability || 0)}٪</dd></div><div><dt>ریسک</dt><dd>{selectedOpportunity.risk_label || "نامشخص"}</dd></div><div><dt>آخرین فعالیت</dt><dd>{displayDateTime(selectedOpportunity.last_activity_at)}</dd></div></dl></article><article><h3>شرح</h3><p>{selectedOpportunity.description || "شرح ثبت نشده است."}</p></article></div>}
        {detailSection === "followup" && <div className={styles.detailColumns}><article><h3>اقدام بعدی</h3><dl><div><dt>اقدام</dt><dd>{selectedOpportunity.next_action}</dd></div><div><dt>تاریخ اقدام</dt><dd>{displayDateTime(selectedOpportunity.next_action_due)}</dd></div><div><dt>زمان باقی‌مانده</dt><dd>{actionUrgency(selectedOpportunity.next_action_due).remaining}</dd></div></dl><button className={styles.fullButton} onClick={() => followUpOpportunity(selectedOpportunity)}>ثبت پیگیری</button></article><article><h3>یادداشت‌ها</h3><ul>{(selectedOpportunity.notes || []).map((note) => <li key={note}>{note}</li>)}</ul></article></div>}
        {detailSection === "documents" && <div className={styles.documentList}>{(selectedOpportunity.documents || []).map((document) => <button key={document}><span>▤</span><b>{document}</b><small>فایل خصوصی سامانه</small></button>)}{!selectedOpportunity.documents?.length && <p>سندی ثبت نشده است.</p>}</div>}
        {detailSection === "more" && <div className={styles.detailColumns}><article><h3>اطلاعات بیشتر</h3><p>فرصت‌های مستقیم می‌توانند پس از تکمیل اطلاعات به مناقصه، استعلام یا قرارداد تبدیل شوند؛ این تبدیل بدون ورود دوباره اطلاعات انجام خواهد شد.</p></article><article><h3>عملیات</h3><div className={styles.modalActions}><button onClick={() => changeOpportunityStage(selectedOpportunity)}>تغییر مرحله</button><button onClick={() => notify("تبدیل به مناقصه یا استعلام پس از تأیید مدیر انجام می‌شود.")}>تبدیل به فراخوان</button><button onClick={() => notify("تبدیل به قرارداد فقط پس از نتیجه موفق و تأیید مدیر انجام می‌شود.")}>تبدیل به قرارداد</button><button className={styles.dangerAction} onClick={() => removeOpportunity(selectedOpportunity)}>حذف از فهرست</button></div></article></div>}
      </div>
    </section></div>}
  </main>;
}
