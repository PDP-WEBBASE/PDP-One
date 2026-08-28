"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT } from "./procurementUiSync";
import {
  getProcurementStableViewState,
  PROCUREMENT_STABLE_VIEW_STATE_EVENT,
  stableWorkflowLabel,
} from "./procurementStableViewState";

type Option = { value: string; label: string };
type V9Window = Window & {
  __pdpPaginationPage?: number;
  __pdpStableListCache?: Map<string, unknown>;
  __pdpV9Sources?: string[];
  __pdpV9Importance?: string[];
  __pdpV9Urgency?: string[];
  __pdpV9DeadlineStatuses?: string[];
  __pdpV9PublishedFrom?: string;
  __pdpV9PublishedTo?: string;
  __pdpV9OpportunityTypes?: string[];
  __pdpV9ActivityDomains?: string[];
  __pdpV9Provinces?: string[];
};

const CLEAR_EVENT = "pdp-procurement-v9-clear-filters";
const NOTICE_DATA_EVENT = "pdp-procurement-compact-notice-data";
const DIRECT_DATA_EVENT = "pdp-procurement-direct-page-data";
const fa = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" });
const faMonth = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", timeZone: "UTC" });
const persianParts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric", day: "numeric", timeZone: "UTC" });

const sourceOptions: Option[] = [
  { value: "ستاد ایران", label: "ستاد ایران" },
  { value: "هزاره", label: "هزاره" },
  { value: "پارس‌نماد", label: "پارس‌نماد" },
];
const importanceOptions: Option[] = [
  { value: "low", label: "کم" }, { value: "medium", label: "متوسط" },
  { value: "high", label: "زیاد" }, { value: "very_high", label: "بسیار زیاد" },
];
const urgencyOptions: Option[] = [
  { value: "critical", label: "بحرانی" }, { value: "high", label: "زیاد" },
  { value: "medium", label: "متوسط" }, { value: "normal", label: "کم" },
  { value: "unknown", label: "نامشخص" },
];
const deadlineOptions: Option[] = [
  { value: "expired", label: "منقضی شده" }, { value: "expiring", label: "در حال انقضا" },
  { value: "available", label: "فرصت دارد" }, { value: "unknown", label: "نامشخص" },
];
const opportunityOptions: Option[] = [
  { value: "consulting", label: "مشاوره" }, { value: "epc", label: "EPC" },
  { value: "construction", label: "احداث" }, { value: "unclassified", label: "نامشخص / نیازمند تشخیص" },
];
const activityDomainOptions: Option[] = [
  { value: "building", label: "ساختمان و معماری" },
  { value: "urban", label: "شهرسازی، برنامه‌ریزی و توسعه" },
  { value: "mep", label: "تأسیسات و زیرساخت" },
  { value: "renewable", label: "انرژی‌های تجدیدپذیر" },
  { value: "multi", label: "ترکیبی / بین‌حوزه‌ای" },
  { value: "undetermined", label: "نامشخص / نیازمند تشخیص" },
];
const provinceOptions: Option[] = [
  "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", "بوشهر", "تهران",
  "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی", "خوزستان", "زنجان", "سمنان",
  "سیستان و بلوچستان", "فارس", "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد",
  "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد",
].map((label) => ({ value: label, label }));

const TYPE_STORAGE_KEY = "pdp-one.procurement.opportunity-types.v1";
const DOMAIN_STORAGE_KEY = "pdp-one.procurement.activity-domains.v1";

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function currentSection() {
  const state = getProcurementStableViewState();
  if (!["tenders", "inquiries", "direct"].includes(state.top)) return null;
  const expected = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
    (candidate) => !candidate.closest("nav") && normalize(candidate.textContent) === expected,
  );
  return button?.closest("section") as HTMLElement | null;
}

function statusTone(value: string) {
  const text = normalize(value);
  if (text.includes("بسیار زیاد") || text.includes("بحرانی") || text.includes("گذشته") || text.includes("منقضی")) return "danger";
  if (text.includes("زیاد")) return "high";
  if (text.includes("متوسط")) return "medium";
  if (text.includes("کم") || text.includes("عادی")) return "safe";
  return "neutral";
}

function normalizeMetadataBadges(section: HTMLElement) {
  section.querySelectorAll<HTMLElement>(".pdp-v2-meta-row").forEach((row) => {
    row.querySelectorAll<HTMLElement>(":scope > *").forEach((badge) => {
      badge.classList.remove("pdp-v9-neutral", "pdp-v9-danger", "pdp-v9-high", "pdp-v9-medium", "pdp-v9-safe");
      const text = normalize(badge.textContent);
      const isStatus = text.startsWith("اهمیت")
        || text.startsWith("فوریت")
        || text === "عادی"
        || text.includes("تاریخ نامشخص")
        || badge.classList.contains("pdp-deadline-date");
      badge.classList.add(`pdp-v9-${isStatus ? statusTone(text) : "neutral"}`);
    });

    const deadline = row.querySelector<HTMLElement>(".pdp-deadline-date");
    if (!deadline) return;
    const article = deadline.closest("article");
    const urgencyBadge = Array.from(article?.querySelectorAll<HTMLElement>(".pdp-v2-status-row > *") || []).find((badge) => {
      const text = normalize(badge.textContent);
      return text.startsWith("فوریت") || text === "عادی" || text.includes("مهلت گذشته") || text.includes("تاریخ نامشخص");
    });
    const tone = statusTone(urgencyBadge?.textContent || deadline.textContent || "");
    deadline.classList.remove("pdp-v9-neutral", "pdp-v9-danger", "pdp-v9-high", "pdp-v9-medium", "pdp-v9-safe");
    deadline.classList.add(`pdp-v9-${tone}`);
  });
}

function syncPresentation() {
  const section = currentSection();
  if (!section) return;
  section.querySelectorAll<HTMLElement>("article[data-pdp-direct-id]").forEach((article) => {
    const content = article.children.item(0) as HTMLElement | null;
    const decision = article.children.item(1) as HTMLElement | null;
    const status = content?.firstElementChild?.lastElementChild as HTMLElement | null;
    status?.classList.add("pdp-v9-direct-status");
    decision?.querySelector("dl")?.classList.add("pdp-v9-responsible-hidden");
  });
  normalizeMetadataBadges(section);
}

let publishFrame = 0;
function publish(next: Partial<V9Window>) {
  if (typeof window === "undefined") return;
  const guarded = window as V9Window;
  Object.assign(guarded, next);
  guarded.__pdpPaginationPage = 1;
  guarded.__pdpStableListCache?.clear();
  window.cancelAnimationFrame(publishFrame);
  publishFrame = window.requestAnimationFrame(() => {
    emitProcurementUiSync({ source: "procurement-web-preview-v9", bulkWorkspace: true });
  });
}

function selectedLabel(values: string[], options: Option[], empty: string, namesAlways = false) {
  if (values.length === options.length) return empty;
  if (!values.length) return "هیچ‌کدام";
  const labels = values.map((value) => options.find((option) => option.value === value)?.label || value);
  if (namesAlways || labels.length === 1) return labels.join("، ");
  return `${fa.format(labels.length)} مورد انتخاب شده`;
}

function MultiSelect({ title, values, options, empty, namesAlways, onChange }: {
  title: string; values: string[]; options: Option[]; empty: string; namesAlways?: boolean; onChange: (values: string[]) => void;
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const allSelected = options.length > 0 && values.length === options.length;
  const partlySelected = values.length > 0 && !allSelected;
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (detailsRef.current?.open && event.target instanceof Node && !detailsRef.current.contains(event.target)) detailsRef.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  const closeOthers = () => {
    if (!detailsRef.current?.open) return;
    document.querySelectorAll<HTMLDetailsElement>("details.pdp-v9-select[open]").forEach((details) => {
      if (details !== detailsRef.current) details.open = false;
    });
  };
  return <label className="pdp-v9-field"><span>{title}</span><details ref={detailsRef} className="pdp-v9-select" onToggle={closeOthers}><summary>{selectedLabel(values, options, empty, namesAlways)}</summary><div className="pdp-v9-menu"><label className="pdp-v9-select-all"><input type="checkbox" checked={allSelected} ref={(node) => { if (node) node.indeterminate = partlySelected; }} onChange={(event) => onChange(event.target.checked ? options.map((option) => option.value) : [])} />همه</label>{options.map((option) => <label key={option.value}><input type="checkbox" checked={values.includes(option.value)} onChange={(event) => onChange(event.target.checked ? [...values, option.value] : values.filter((value) => value !== option.value))} />{option.label}</label>)}</div></details></label>;
}

function dateParts(date: Date) {
  const parts = persianParts.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value || 0);
  return { year: read("year"), month: read("month"), day: read("day") };
}

function iso(date: Date) { return date.toISOString().slice(0, 10); }

function daysForPersianMonth(anchor: Date) {
  const target = dateParts(anchor);
  const days: Date[] = [];
  const cursor = new Date(anchor);
  cursor.setUTCDate(cursor.getUTCDate() - 35);
  for (let index = 0; index < 75; index += 1) {
    const candidate = new Date(cursor);
    candidate.setUTCDate(cursor.getUTCDate() + index);
    const parts = dateParts(candidate);
    if (parts.year === target.year && parts.month === target.month) days.push(candidate);
  }
  return days;
}

function JalaliRange({ from, to, onChange }: { from: string; to: string; onChange: (from: string, to: string) => void }) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [anchor, setAnchor] = useState(() => from ? new Date(`${from}T12:00:00Z`) : new Date());
  const days = useMemo(() => daysForPersianMonth(anchor), [anchor]);
  const leading = days.length ? (days[0].getUTCDay() + 1) % 7 : 0;
  const display = from ? `${faDate.format(new Date(`${from}T12:00:00Z`))}${to ? ` تا ${faDate.format(new Date(`${to}T12:00:00Z`))}` : ""}` : "انتخاب بازه";
  const choose = (value: string) => {
    if (!from || to || value < from) onChange(value, "");
    else onChange(from, value);
  };
  const move = (amount: number) => setAnchor((current) => { const next = new Date(current); next.setUTCDate(next.getUTCDate() + amount); return next; });
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (detailsRef.current?.open && event.target instanceof Node && !detailsRef.current.contains(event.target)) detailsRef.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  const closeOthers = () => {
    if (!detailsRef.current?.open) return;
    document.querySelectorAll<HTMLDetailsElement>("details.pdp-v9-select[open]").forEach((details) => {
      if (details !== detailsRef.current) details.open = false;
    });
  };
  return <label className="pdp-v9-field pdp-v9-date-field"><span>تاریخ انتشار</span><details ref={detailsRef} className="pdp-v9-select pdp-v9-calendar" onToggle={closeOthers}><summary>{display}</summary><div className="pdp-v9-calendar-panel"><header><button type="button" onClick={() => move(32)}>‹</button><b>{faMonth.format(anchor)}</b><button type="button" onClick={() => move(-32)}>›</button></header><div className="pdp-v9-week">{["ش", "ی", "د", "س", "چ", "پ", "ج"].map((day) => <span key={day}>{day}</span>)}</div><div className="pdp-v9-days">{Array.from({ length: leading }).map((_, index) => <i key={`blank-${index}`} />)}{days.map((day) => { const value = iso(day); const selected = value === from || value === to; const ranged = from && to && value > from && value < to; return <button type="button" key={value} className={selected ? "selected" : ranged ? "ranged" : ""} onClick={() => choose(value)}>{fa.format(dateParts(day).day)}</button>; })}</div><footer><button type="button" onClick={() => onChange("", "")}>پاک‌کردن بازه</button></footer></div></details></label>;
}

function browserState() {
  return typeof window === "undefined" ? null : window as V9Window;
}

export function resetProcurementV9NativeFilters() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CLEAR_EVENT));
}

export function ProcurementV9NativeFilters({ noticeTab }: { noticeTab: boolean }) {
  const [sources, setSources] = useState<string[]>(() => browserState()?.__pdpV9Sources || sourceOptions.map((option) => option.value));
  const [importance, setImportance] = useState<string[]>(() => browserState()?.__pdpV9Importance || importanceOptions.map((option) => option.value));
  const [urgency, setUrgency] = useState<string[]>(() => browserState()?.__pdpV9Urgency || urgencyOptions.map((option) => option.value));
  const [deadlines, setDeadlines] = useState<string[]>(() => browserState()?.__pdpV9DeadlineStatuses || deadlineOptions.map((option) => option.value));
  const [publishedFrom, setPublishedFrom] = useState(() => browserState()?.__pdpV9PublishedFrom || "");
  const [publishedTo, setPublishedTo] = useState(() => browserState()?.__pdpV9PublishedTo || "");
  const [provinces, setProvinces] = useState<string[]>(() => browserState()?.__pdpV9Provinces || provinceOptions.map((option) => option.value));

  useEffect(() => {
    publish({ __pdpV9Sources: sources, __pdpV9Importance: importance, __pdpV9Urgency: urgency, __pdpV9DeadlineStatuses: deadlines, __pdpV9PublishedFrom: publishedFrom, __pdpV9PublishedTo: publishedTo, __pdpV9Provinces: provinces });
  }, [sources, importance, urgency, deadlines, publishedFrom, publishedTo, provinces]);

  useEffect(() => {
    const clear = () => {
      setSources(sourceOptions.map((option) => option.value));
      setImportance(importanceOptions.map((option) => option.value));
      setUrgency(urgencyOptions.map((option) => option.value));
      setDeadlines(deadlineOptions.map((option) => option.value));
      setPublishedFrom("");
      setPublishedTo("");
      setProvinces(provinceOptions.map((option) => option.value));
    };
    window.addEventListener(CLEAR_EVENT, clear);
    return () => window.removeEventListener(CLEAR_EVENT, clear);
  }, []);

  return <div className="pdp-v9-filter-grid" dir="rtl">
    {noticeTab && <MultiSelect title="منبع" values={sources} options={sourceOptions} empty="همه منابع" onChange={setSources} />}
    <MultiSelect title="استان" values={provinces} options={provinceOptions} empty="همه استان‌ها" onChange={setProvinces} />
    <MultiSelect title="اهمیت" values={importance} options={importanceOptions} empty="همه سطوح" onChange={setImportance} />
    <MultiSelect title="فوریت" values={urgency} options={urgencyOptions} empty="همه وضعیت‌ها" onChange={setUrgency} />
    {noticeTab && <>
      <MultiSelect title="وضعیت مهلت" values={deadlines} options={deadlineOptions} empty="همه وضعیت‌ها" onChange={setDeadlines} />
      <JalaliRange from={publishedFrom} to={publishedTo} onChange={(from, to) => { setPublishedFrom(from); setPublishedTo(to); }} />
    </>}
  </div>;
}

export function ProcurementV9NativeToolbar() {
  const [opportunities, setOpportunities] = useState<string[]>(() => browserState()?.__pdpV9OpportunityTypes || ["consulting", "epc"]);
  const [domains, setDomains] = useState<string[]>(() => browserState()?.__pdpV9ActivityDomains || activityDomainOptions.map((option) => option.value));

  useEffect(() => {
    try {
      const storedTypes = JSON.parse(localStorage.getItem(TYPE_STORAGE_KEY) || "null") as string[] | null;
      const storedDomains = JSON.parse(localStorage.getItem(DOMAIN_STORAGE_KEY) || "null") as string[] | null;
      if (Array.isArray(storedTypes)) setOpportunities(storedTypes);
      if (Array.isArray(storedDomains)) setDomains(storedDomains);
    } catch { /* Invalid legacy browser state is ignored. */ }
  }, []);

  useEffect(() => {
    publish({ __pdpV9OpportunityTypes: opportunities, __pdpV9ActivityDomains: domains });
    localStorage.setItem(TYPE_STORAGE_KEY, JSON.stringify(opportunities));
    localStorage.setItem(DOMAIN_STORAGE_KEY, JSON.stringify(domains));
  }, [opportunities, domains]);

  return <div className="pdp-v9-toolbar" dir="rtl">
    <MultiSelect title="حوزه فعالیت" values={domains} options={activityDomainOptions} empty="همه حوزه‌ها" namesAlways onChange={setDomains} />
    <MultiSelect title="نوع فرصت" values={opportunities} options={opportunityOptions} empty="همه انواع" namesAlways onChange={setOpportunities} />
    <div id="pdp-procurement-v9-bulk-slot" />
  </div>;
}

export default function ProcurementWebPreviewV9Enhancement() {
  useEffect(() => {
    let frame1 = 0;
    let frame2 = 0;
    const schedule = () => {
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
      frame1 = window.requestAnimationFrame(() => {
        frame2 = window.requestAnimationFrame(syncPresentation);
      });
    };
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
    window.addEventListener(NOTICE_DATA_EVENT, schedule);
    window.addEventListener(DIRECT_DATA_EVENT, schedule);
    schedule();
    return () => {
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
      window.removeEventListener(NOTICE_DATA_EVENT, schedule);
      window.removeEventListener(DIRECT_DATA_EVENT, schedule);
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
    };
  }, []);

  return <><style>{`
    .pdp-v9-native-filter{display:none!important}.pdp-v9-filter-bar>label:has(>select){display:none!important}.pdp-v9-filter-bar{grid-template-columns:minmax(230px,1.55fr) repeat(6,minmax(108px,.72fr)) minmax(225px,1.18fr) auto!important;gap:6px!important;align-items:end!important;padding:9px!important}.pdp-v9-filter-bar>label{font-size:12px!important;line-height:1.25!important;font-weight:700!important;gap:4px!important}.pdp-v9-filter-bar>label input,.pdp-v9-filter-bar>label select{min-height:34px!important;padding:5px 7px!important;font-size:11.5px!important;line-height:1.2!important;font-weight:400!important}.pdp-v9-filter-bar .pdp-v2-clear-group button{min-height:34px!important;padding:4px 9px!important;font-size:12px!important;font-weight:700!important}.pdp-v9-filter-bar .pdp-v2-row-count{display:none!important}
    .pdp-v9-filter-grid{display:contents}.pdp-v9-field{position:relative;display:grid;gap:4px;min-width:0;font-size:12px;line-height:1.25;font-weight:700;color:#17202a}.pdp-v9-select{position:relative;min-width:0;font-weight:400}.pdp-v9-select>summary{display:flex;align-items:center;justify-content:space-between;min-height:34px;padding:5px 8px;border:1px solid rgba(15,23,42,.16);border-radius:8px;background:#fff;color:#17202a;font-size:11.5px;cursor:pointer;list-style:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pdp-v9-select>summary::-webkit-details-marker{display:none}.pdp-v9-select>summary::before{content:"⌄";color:#64748b;font-size:13px;margin-left:8px}.pdp-v9-menu{position:absolute;z-index:60;top:calc(100% + 5px);right:0;min-width:210px;padding:8px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;box-shadow:0 14px 32px rgba(15,23,42,.16)}.pdp-v9-menu label{display:grid;grid-template-columns:18px 1fr 18px;align-items:center;gap:7px;min-height:29px;padding:4px 6px;border-radius:7px;color:#334155;font-size:11px;font-weight:400;white-space:nowrap;text-align:center}.pdp-v9-menu label::after{content:""}.pdp-v9-menu label:hover{background:#f1f5f9}.pdp-v9-menu .pdp-v9-select-all{border-bottom:1px solid #e2e8f0;border-radius:0;margin-bottom:4px;font-weight:700}.pdp-v9-menu input{width:15px;height:15px;margin:0;accent-color:#145563}
    .pdp-v9-workflow-row{display:flex!important;align-items:flex-end!important;justify-content:space-between!important;gap:14px!important;width:100%!important;margin-bottom:14px!important;overflow:visible!important}.pdp-v9-workflow-row>.pdp-v9-toolbar{margin-right:auto;flex:0 0 auto}.pdp-v9-toolbar{display:flex;align-items:flex-end;justify-content:flex-end;gap:6px;direction:rtl;overflow:visible}.pdp-v9-toolbar .pdp-v9-field{min-width:165px}.pdp-v9-toolbar .pdp-v9-select>summary{min-height:34px}.pdp-v9-toolbar #pdp-procurement-v9-bulk-slot{display:flex;align-items:flex-end}
    .pdp-v9-calendar-panel{position:absolute;z-index:70;top:calc(100% + 5px);right:0;left:auto;width:304px;padding:11px;border:1px solid #cbd5e1;border-radius:12px;background:#fff;box-shadow:0 16px 34px rgba(15,23,42,.18)}.pdp-v9-calendar-panel header{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}.pdp-v9-calendar-panel header button,.pdp-v9-calendar-panel footer button{border:1px solid #dbe3ec;border-radius:8px;background:#fff;padding:4px 9px;font:inherit;cursor:pointer}.pdp-v9-week,.pdp-v9-days{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}.pdp-v9-week span{text-align:center;color:#64748b;font-size:10px}.pdp-v9-days i{min-height:31px}.pdp-v9-days button{min-height:31px;border:0;border-radius:7px;background:#fff;font:inherit;font-size:10.5px;cursor:pointer}.pdp-v9-days button:hover,.pdp-v9-days button.ranged{background:#e3eef0}.pdp-v9-days button.selected{background:#145563;color:#fff;font-weight:700}.pdp-v9-calendar-panel footer{margin-top:8px;text-align:left}
    .pdp-v2-selected-count,.pdp-ux-selected-count{display:none!important}.pdp-v2-decision>dl,.pdp-ux-record>div:last-child>dl{display:none!important}.pdp-v2-meta-row>*{box-sizing:border-box;min-height:22px!important;padding:2px 8px!important;border-radius:999px!important;font-size:10.5px!important;line-height:1.45!important;font-weight:700!important}.pdp-v2-meta-row button{font-size:10.5px!important}.pdp-v9-neutral{border-color:#cbd5e1!important;background:#f8fafc!important;color:#334155!important}.pdp-v9-danger{border-color:#fecdd3!important;background:#fff1f2!important;color:#be123c!important}.pdp-v9-high{border-color:#fed7aa!important;background:#fff7ed!important;color:#c2410c!important}.pdp-v9-medium{border-color:#eadb94!important;background:#fff9dd!important;color:#776210!important}.pdp-v9-safe{border-color:#99f6e4!important;background:#f0fdfa!important;color:#0f766e!important}
    .pdp-v9-responsible-hidden{display:none!important}.pdp-v9-direct-status>*{box-sizing:border-box;min-height:22px!important;padding:2px 8px!important;border-radius:999px!important;font-size:10.5px!important;line-height:1.45!important;font-weight:700!important}
    @media(max-width:1450px){.pdp-v9-filter-bar{grid-template-columns:minmax(220px,1.4fr) repeat(6,minmax(88px,.7fr)) minmax(130px,.75fr)!important}}
    @media(max-width:980px){.pdp-v9-workflow-row{flex-wrap:wrap!important}.pdp-v9-workflow-row>.pdp-v9-toolbar{margin-right:0;width:100%}.pdp-v9-filter-bar{grid-template-columns:repeat(2,minmax(0,1fr))!important}.pdp-v9-filter-grid{display:contents}.pdp-v9-calendar-panel{right:0;left:auto;max-width:calc(100vw - 32px)}}
  `}</style></>;
}
