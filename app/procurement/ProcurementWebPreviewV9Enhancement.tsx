"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
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
};

const FILTER_HOST_ID = "pdp-procurement-v9-filter-host";
const TOOLBAR_HOST_ID = "pdp-procurement-v9-toolbar-host";
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
  { value: "consulting", label: "مشاوره" }, { value: "epc", label: "EPC" }, { value: "construction", label: "احداث" },
];

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

function findFilterBar(section: HTMLElement) {
  const search = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("جست‌وجو"));
  return search?.parentElement as HTMLElement | null;
}

function hideNativeFilter(filterBar: HTMLElement, prefix: string) {
  Array.from(filterBar.querySelectorAll<HTMLLabelElement>("label")).forEach((label) => {
    if (normalize(label.textContent).startsWith(prefix)) label.classList.add("pdp-v9-native-filter");
  });
}

function ensureHosts() {
  const section = currentSection();
  if (!section) return { filter: null, toolbar: null };
  const filterBar = findFilterBar(section);
  if (!filterBar) return { filter: null, toolbar: null };
  filterBar.classList.add("pdp-v9-filter-bar");
  hideNativeFilter(filterBar, "منبع");
  hideNativeFilter(filterBar, "اهمیت");
  hideNativeFilter(filterBar, "فوریت");
  hideNativeFilter(filterBar, "وضعیت مهلت");
  hideNativeFilter(filterBar, "تاریخ انتشار");
  filterBar.querySelectorAll<HTMLElement>(".pdp-v2-row-count").forEach((node) => { node.style.display = "none"; });
  section.querySelectorAll<HTMLElement>("article[data-pdp-direct-id]").forEach((article) => {
    const content = article.children.item(0) as HTMLElement | null;
    const decision = article.children.item(1) as HTMLElement | null;
    const status = content?.firstElementChild?.lastElementChild as HTMLElement | null;
    status?.classList.add("pdp-v9-direct-status");
    decision?.querySelector("dl")?.classList.add("pdp-v9-responsible-hidden");
  });

  let filter = filterBar.querySelector<HTMLElement>(`#${FILTER_HOST_ID}`);
  if (!filter) {
    filter = document.createElement("div");
    filter.id = FILTER_HOST_ID;
    const clearGroup = Array.from(filterBar.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent).startsWith("پاک"))?.parentElement;
    filterBar.insertBefore(filter, clearGroup || null);
  }

  const workflowButton = Array.from(section.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent) === stableWorkflowLabel());
  const workflowRow = workflowButton?.parentElement as HTMLElement | null;
  let toolbar = workflowRow?.querySelector<HTMLElement>(`#${TOOLBAR_HOST_ID}`) || null;
  if (workflowRow) {
    workflowRow.classList.add("pdp-v9-workflow-row");
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.id = TOOLBAR_HOST_ID;
      workflowRow.appendChild(toolbar);
    }
  }
  return { filter, toolbar };
}

function publish(next: Partial<V9Window>) {
  const guarded = window as V9Window;
  Object.assign(guarded, next);
  guarded.__pdpPaginationPage = 1;
  guarded.__pdpStableListCache?.clear();
  emitProcurementUiSync({ source: "procurement-web-preview-v9", bulkWorkspace: true });
}

function selectedLabel(values: string[], options: Option[], empty: string, namesAlways = false) {
  if (!values.length) return empty;
  const labels = values.map((value) => options.find((option) => option.value === value)?.label || value);
  if (namesAlways || labels.length === 1) return labels.join("، ");
  return `${fa.format(labels.length)} مورد انتخاب شده`;
}

function MultiSelect({ title, values, options, empty, namesAlways, onChange }: {
  title: string; values: string[]; options: Option[]; empty: string; namesAlways?: boolean; onChange: (values: string[]) => void;
}) {
  return <label className="pdp-v9-field"><span>{title}</span><details className="pdp-v9-select"><summary>{selectedLabel(values, options, empty, namesAlways)}</summary><div className="pdp-v9-menu">{options.map((option) => <label key={option.value}><input type="checkbox" checked={values.includes(option.value)} onChange={(event) => onChange(event.target.checked ? [...values, option.value] : values.filter((value) => value !== option.value))} />{option.label}</label>)}</div></details></label>;
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
  const [anchor, setAnchor] = useState(() => from ? new Date(`${from}T12:00:00Z`) : new Date());
  const days = useMemo(() => daysForPersianMonth(anchor), [anchor]);
  const leading = days.length ? (days[0].getUTCDay() + 1) % 7 : 0;
  const display = from ? `${faDate.format(new Date(`${from}T12:00:00Z`))}${to ? ` تا ${faDate.format(new Date(`${to}T12:00:00Z`))}` : ""}` : "انتخاب بازه";
  const choose = (value: string) => {
    if (!from || to || value < from) onChange(value, "");
    else onChange(from, value);
  };
  const move = (amount: number) => setAnchor((current) => { const next = new Date(current); next.setUTCDate(next.getUTCDate() + amount); return next; });
  return <label className="pdp-v9-field pdp-v9-date-field"><span>تاریخ انتشار</span><details className="pdp-v9-select pdp-v9-calendar"><summary>{display}</summary><div className="pdp-v9-calendar-panel"><header><button type="button" onClick={() => move(32)}>‹</button><b>{faMonth.format(anchor)}</b><button type="button" onClick={() => move(-32)}>›</button></header><div className="pdp-v9-week">{["ش", "ی", "د", "س", "چ", "پ", "ج"].map((day) => <span key={day}>{day}</span>)}</div><div className="pdp-v9-days">{Array.from({ length: leading }).map((_, index) => <i key={`blank-${index}`} />)}{days.map((day) => { const value = iso(day); const selected = value === from || value === to; const ranged = from && to && value > from && value < to; return <button type="button" key={value} className={selected ? "selected" : ranged ? "ranged" : ""} onClick={() => choose(value)}>{fa.format(dateParts(day).day)}</button>; })}</div><footer><button type="button" onClick={() => onChange("", "")}>پاک‌کردن بازه</button></footer></div></details></label>;
}

export default function ProcurementWebPreviewV9Enhancement() {
  const guarded = window as V9Window;
  const [filterHost, setFilterHost] = useState<HTMLElement | null>(null);
  const [toolbarHost, setToolbarHost] = useState<HTMLElement | null>(null);
  const [sources, setSources] = useState<string[]>(guarded.__pdpV9Sources || []);
  const [importance, setImportance] = useState<string[]>(guarded.__pdpV9Importance || []);
  const [urgency, setUrgency] = useState<string[]>(guarded.__pdpV9Urgency || []);
  const [deadlines, setDeadlines] = useState<string[]>(guarded.__pdpV9DeadlineStatuses || []);
  const [opportunities, setOpportunities] = useState<string[]>(guarded.__pdpV9OpportunityTypes || ["consulting", "epc"]);
  const [publishedFrom, setPublishedFrom] = useState(guarded.__pdpV9PublishedFrom || "");
  const [publishedTo, setPublishedTo] = useState(guarded.__pdpV9PublishedTo || "");
  const [, setRevision] = useState(0);

  const sync = useCallback(() => {
    const hosts = ensureHosts();
    setFilterHost((current) => current === hosts.filter ? current : hosts.filter);
    setToolbarHost((current) => current === hosts.toolbar ? current : hosts.toolbar);
    setRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    let frame = 0;
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(sync); };
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
    document.addEventListener("click", schedule, true);
    schedule();
    return () => { window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule); window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule); document.removeEventListener("click", schedule, true); cancelAnimationFrame(frame); };
  }, [sync]);

  useEffect(() => {
    publish({ __pdpV9Sources: sources, __pdpV9Importance: importance, __pdpV9Urgency: urgency, __pdpV9DeadlineStatuses: deadlines, __pdpV9OpportunityTypes: opportunities, __pdpV9PublishedFrom: publishedFrom, __pdpV9PublishedTo: publishedTo });
  }, [sources, importance, urgency, deadlines, opportunities, publishedFrom, publishedTo]);

  useEffect(() => {
    const clear = (event: Event) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      if (!button || !normalize(button.textContent).startsWith("پاک") || !currentSection()?.contains(button)) return;
      setSources([]);
      setImportance([]);
      setUrgency([]);
      setDeadlines([]);
      setPublishedFrom("");
      setPublishedTo("");
      setOpportunities(["consulting", "epc"]);
    };
    document.addEventListener("click", clear, true);
    return () => document.removeEventListener("click", clear, true);
  }, []);

  const state = getProcurementStableViewState();
  const noticeTab = state.top === "tenders" || state.top === "inquiries";
  const filters = filterHost ? createPortal(<div className="pdp-v9-filter-grid" dir="rtl">{noticeTab && <MultiSelect title="منبع" values={sources} options={sourceOptions} empty="همه منابع" onChange={setSources} />}<MultiSelect title="اهمیت" values={importance} options={importanceOptions} empty="همه سطوح" onChange={setImportance} /><MultiSelect title="فوریت" values={urgency} options={urgencyOptions} empty="همه وضعیت‌ها" onChange={setUrgency} />{noticeTab && <><MultiSelect title="وضعیت مهلت" values={deadlines} options={deadlineOptions} empty="همه وضعیت‌ها" onChange={setDeadlines} /><JalaliRange from={publishedFrom} to={publishedTo} onChange={(from, to) => { setPublishedFrom(from); setPublishedTo(to); }} /></>}</div>, filterHost) : null;
  const toolbar = toolbarHost ? createPortal(<div className="pdp-v9-toolbar" dir="rtl"><MultiSelect title="نوع فرصت" values={opportunities} options={opportunityOptions} empty="انتخاب نوع فرصت" namesAlways onChange={setOpportunities} /><div id="pdp-procurement-v9-bulk-slot" /></div>, toolbarHost) : null;

  return <><style>{`
    .pdp-v9-native-filter{display:none!important}.pdp-v9-filter-bar{grid-template-columns:minmax(260px,1.5fr) minmax(130px,.7fr) minmax(130px,.7fr)!important;gap:10px!important}.pdp-v9-filter-bar>label{font-size:13px!important;font-weight:700!important;gap:5px!important}.pdp-v9-filter-bar>label input,.pdp-v9-filter-bar>label select{font-size:12px!important;font-weight:400!important}.pdp-v9-filter-bar .pdp-v2-clear-group button{font-size:13px!important;font-weight:700!important}.pdp-v9-filter-bar .pdp-v2-row-count{display:none!important}
    #${FILTER_HOST_ID}{display:contents}.pdp-v9-filter-grid{display:contents}.pdp-v9-field{position:relative;display:grid;gap:5px;min-width:0;font-size:13px;font-weight:700;color:#263238}.pdp-v9-select{position:relative;min-width:0;font-weight:400}.pdp-v9-select>summary{display:flex;align-items:center;justify-content:space-between;min-height:36px;padding:6px 10px;border:1px solid #cbd5e1;border-radius:9px;background:#fff;color:#334155;font-size:12px;cursor:pointer;list-style:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pdp-v9-select>summary::-webkit-details-marker{display:none}.pdp-v9-select>summary::before{content:"⌄";font-size:12px;margin-left:8px}.pdp-v9-menu{position:absolute;z-index:60;top:calc(100% + 4px);right:0;min-width:100%;padding:6px;border:1px solid #dbe3ec;border-radius:10px;background:#fff;box-shadow:0 12px 28px rgba(15,23,42,.14)}.pdp-v9-menu label{display:flex;align-items:center;gap:8px;padding:7px;border-radius:7px;font-size:12px;font-weight:400;white-space:nowrap}.pdp-v9-menu label:hover{background:#f1f5f9}.pdp-v9-menu input{width:16px;height:16px;margin:0;accent-color:#145563}
    .pdp-v9-workflow-row{display:flex!important;align-items:center!important;gap:8px!important;width:100%!important}.pdp-v9-workflow-row #${TOOLBAR_HOST_ID}{margin-right:auto}.pdp-v9-toolbar{display:flex;align-items:end;gap:8px}.pdp-v9-toolbar .pdp-v9-field{min-width:205px}.pdp-v9-toolbar .pdp-v9-select>summary{min-height:40px;border-radius:11px}.pdp-v9-toolbar #pdp-procurement-v9-bulk-slot{display:flex;align-items:center}
    .pdp-v9-calendar-panel{position:absolute;z-index:70;top:calc(100% + 4px);left:0;width:310px;padding:10px;border:1px solid #dbe3ec;border-radius:12px;background:#fff;box-shadow:0 14px 34px rgba(15,23,42,.16)}.pdp-v9-calendar-panel header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.pdp-v9-calendar-panel header button,.pdp-v9-calendar-panel footer button{border:1px solid #dbe3ec;border-radius:7px;background:#fff;padding:4px 9px;font:inherit;cursor:pointer}.pdp-v9-week,.pdp-v9-days{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}.pdp-v9-week span{text-align:center;color:#64748b;font-size:10px}.pdp-v9-days i{min-height:32px}.pdp-v9-days button{min-height:32px;border:0;border-radius:7px;background:#fff;font:inherit;font-size:11px;cursor:pointer}.pdp-v9-days button:hover,.pdp-v9-days button.ranged{background:#e6f3f5}.pdp-v9-days button.selected{background:#145563;color:#fff;font-weight:700}.pdp-v9-calendar-panel footer{margin-top:8px;text-align:left}
    .pdp-v2-selected-count,.pdp-ux-selected-count{display:none!important}.pdp-v2-decision>dl,.pdp-ux-record>div:last-child>dl{display:none!important}.pdp-v2-meta-row>*{box-sizing:border-box;min-height:24px!important;padding:3px 8px!important;border-radius:8px!important;font-size:10.5px!important;font-weight:400!important}.pdp-v2-meta-row button{font-size:10.5px!important}.pdp-v2-source-row .pdp-compact-source,.pdp-v2-info-row .pdp-compact-chip{border-color:#d7e1ec!important;background:#f8fafc!important;color:#334155!important}.pdp-v2-info-row .pdp-deadline-date{border-color:#fed7aa!important;background:#fff7ed!important;color:#9a3412!important}
    .pdp-v9-responsible-hidden{display:none!important}.pdp-v9-direct-status>*{box-sizing:border-box;min-height:24px!important;padding:3px 8px!important;border-radius:8px!important;font-size:10.5px!important;line-height:1.4!important;font-weight:400!important}
    @media(min-width:1451px){.pdp-v9-filter-bar{grid-template-columns:minmax(260px,1.5fr) minmax(120px,.65fr) repeat(5,minmax(130px,.72fr)) minmax(120px,.65fr)!important}}
    @media(max-width:980px){.pdp-v9-workflow-row{flex-wrap:wrap!important}.pdp-v9-workflow-row #${TOOLBAR_HOST_ID}{margin-right:0;width:100%}.pdp-v9-filter-bar{grid-template-columns:repeat(2,minmax(0,1fr))!important}.pdp-v9-filter-grid{display:contents}.pdp-v9-calendar-panel{right:0;left:auto;max-width:calc(100vw - 32px)}}
  `}</style>{filters}{toolbar}</>;
}
