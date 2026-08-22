"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { emitProcurementUiSync, PROCUREMENT_UI_SYNC_EVENT } from "./procurementUiSync";
import {
  getProcurementStableViewState,
  PROCUREMENT_STABLE_VIEW_STATE_EVENT,
  stableWorkflowLabel,
  type ProcurementStableViewState,
} from "./procurementStableViewState";

type SourceBadge = { key?: string; name: string; source_url?: string; detail_url?: string };
type NoticeRow = {
  id: string;
  title: string;
  employer_name: string;
  province?: string;
  submission_deadline?: string | null;
  sources?: SourceBadge[];
};
type NoticePayload = { count?: number; page_size?: number; results?: NoticeRow[] };
type BulkResponse = {
  dismissed?: number;
  removed?: number;
  blocked?: number;
  detail?: string;
  notice_deleted?: boolean;
};
type StableWindow = Window & {
  __pdpStableListCache?: Map<string, unknown>;
  __pdpPaginationPage?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const RECOMMENDED_BULK_PATH = `${PROCUREMENT_API}/ui/recommendations/dismiss-bulk/`;
const WORKFLOW_BULK_PATH = `${PROCUREMENT_API}/ui/workflow/remove-bulk/`;
const NOTICE_DATA_EVENT = "pdp-procurement-compact-notice-data";
const ROW_TOGGLE_EVENT = "pdp-procurement-v2-row-toggle";
const BULK_HOST_ID = "pdp-procurement-v2-bulk-host";
const OLD_BULK_HOST_ID = "pdp-procurement-ux-bulk-host";
const FILTER_HOST_ID = "pdp-procurement-compact-filter-host";
const ACTION_ATTRIBUTE = "data-pdp-stable-workflow-action";
const SUPPORTED_WORKFLOWS = new Set(["recent", "recommended", "selected", "submitted", "results"]);
const fa = new Intl.NumberFormat("fa-IR");

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function stateSupportsBulk(state: ProcurementStableViewState) {
  return (state.top === "tenders" || state.top === "inquiries") && SUPPORTED_WORKFLOWS.has(state.workflow);
}

function currentSection(state: ProcurementStableViewState) {
  if (state.top !== "tenders" && state.top !== "inquiries") return null;
  const expected = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
    (candidate) => !candidate.closest("nav") && normalize(candidate.textContent) === expected,
  );
  return button?.closest("section") as HTMLElement | null;
}

function findArticle(section: HTMLElement, item: NoticeRow) {
  const identified = Array.from(section.querySelectorAll<HTMLElement>("article[data-pdp-notice-id]")).find(
    (article) => article.dataset.pdpNoticeId === item.id,
  );
  if (identified) return identified;
  const title = normalize(item.title);
  const employer = normalize(item.employer_name);
  return Array.from(section.querySelectorAll<HTMLElement>("article")).find((article) => {
    const heading = normalize(article.querySelector("h3")?.textContent);
    const paragraph = normalize(article.querySelector("p")?.textContent);
    return (
      (heading === title && (!employer || paragraph === employer))
      || (heading.length > 12 && title.startsWith(heading.replace(/…$/, "")))
    );
  }) || null;
}

function findFilterBar(section: HTMLElement) {
  const searchLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) =>
    normalize(label.textContent).startsWith("جست‌وجو"),
  );
  return searchLabel?.parentElement as HTMLElement | null;
}

function sourceRank(value: string) {
  const token = normalize(value).toLocaleLowerCase("fa");
  if (token.includes("setad") || token.includes("ستاد")) return 0;
  if (token.includes("hezareh") || token.includes("هزاره")) return 1;
  if (token.includes("parsnamad") || token.includes("پارس")) return 2;
  return 3;
}

function infoRank(value: string) {
  const token = normalize(value);
  if (token.startsWith("مهلت:")) return 0;
  if (token.includes("باقی‌مانده") || token.includes("منقضی")) return 1;
  return 2;
}

function cloneVisual(node: Element) {
  const clone = node.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("input").forEach((input) => input.remove());
  clone.style.removeProperty("display");
  return clone;
}

function createViewProxy(original: HTMLButtonElement) {
  const button = original.cloneNode(true) as HTMLButtonElement;
  button.type = "button";
  button.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    original.click();
  };
  return button;
}

function syncMetadataColumn(article: HTMLElement) {
  const content = article.children.item(0) as HTMLElement | null;
  const decision = article.children.item(1) as HTMLElement | null;
  if (!content || !decision) return;

  article.classList.add("pdp-v2-record");
  content.classList.add("pdp-v2-content");
  decision.classList.add("pdp-v2-decision");

  const recordTop = content.firstElementChild as HTMLElement | null;
  const heading = content.querySelector<HTMLElement>("h3");
  const employer = heading?.nextElementSibling instanceof HTMLParagraphElement ? heading.nextElementSibling : content.querySelector<HTMLElement>("p");
  const facts = Array.from(content.children).find((node) => node !== recordTop && node !== heading && node !== employer && node instanceof HTMLElement && node.querySelector("span")) as HTMLElement | undefined;
  if (recordTop) recordTop.classList.add("pdp-v2-record-top");
  if (heading) heading.classList.add("pdp-v2-title");
  if (employer) employer.classList.add("pdp-v2-employer");
  if (facts) facts.classList.add("pdp-v2-facts");

  const nativeStatus = recordTop?.lastElementChild as HTMLElement | null;
  const badgeGroup = article.querySelector<HTMLElement>("[data-pdp-compact-badges='1']");
  if (nativeStatus) nativeStatus.classList.add("pdp-v2-native-status-hidden");
  if (badgeGroup) badgeGroup.classList.add("pdp-v2-native-badges-hidden");

  let meta = content.querySelector<HTMLElement>("[data-pdp-v2-meta='1']");
  if (!meta) {
    meta = document.createElement("div");
    meta.dataset.pdpV2Meta = "1";
    meta.className = "pdp-v2-meta";
    content.appendChild(meta);
  }
  meta.replaceChildren();

  const statusRow = document.createElement("div");
  statusRow.className = "pdp-v2-meta-row pdp-v2-status-row";
  if (nativeStatus) {
    const directChildren = Array.from(nativeStatus.children).filter((node) => node !== badgeGroup);
    const viewButton = directChildren.find((node) => node instanceof HTMLButtonElement && normalize(node.textContent) === "مشاهده") as HTMLButtonElement | undefined;
    const importance = directChildren.find((node) => node instanceof HTMLSpanElement && normalize(node.textContent).startsWith("اهمیت"));
    const urgency = directChildren.find((node) => node instanceof HTMLSpanElement && node !== importance && !normalize(node.textContent).includes("منبع"));
    if (viewButton) statusRow.appendChild(createViewProxy(viewButton));
    if (urgency) statusRow.appendChild(cloneVisual(urgency));
    if (importance) statusRow.appendChild(cloneVisual(importance));
  }

  const sourceRow = document.createElement("div");
  sourceRow.className = "pdp-v2-meta-row pdp-v2-source-row";
  if (badgeGroup) {
    const sources = Array.from(badgeGroup.querySelectorAll<HTMLAnchorElement>("a.pdp-compact-source"));
    sources.sort((a, b) => sourceRank(a.textContent || "") - sourceRank(b.textContent || ""));
    sources.forEach((source) => sourceRow.appendChild(cloneVisual(source)));
  }

  const infoRow = document.createElement("div");
  infoRow.className = "pdp-v2-meta-row pdp-v2-info-row";
  if (badgeGroup) {
    const chips = Array.from(badgeGroup.querySelectorAll<HTMLElement>(".pdp-compact-chip"))
      .filter((chip) => !chip.classList.contains("pdp-source-count"));
    chips.sort((a, b) => infoRank(a.textContent || "") - infoRank(b.textContent || ""));
    chips.forEach((chip) => infoRow.appendChild(cloneVisual(chip)));
  }

  if (statusRow.childElementCount) meta.appendChild(statusRow);
  if (sourceRow.childElementCount) meta.appendChild(sourceRow);
  if (infoRow.childElementCount) meta.appendChild(infoRow);

  const nativeAction = Array.from(decision.children).find((node) =>
    node instanceof HTMLElement
    && !node.hasAttribute(ACTION_ATTRIBUTE)
    && Array.from(node.querySelectorAll("button")).some((button) => normalize(button.textContent) === "انتخاب"),
  ) as HTMLElement | undefined;
  nativeAction?.classList.add("pdp-v2-select-action");
  const stableActions = decision.querySelector<HTMLElement>(`[${ACTION_ATTRIBUTE}]`);
  stableActions?.classList.add("pdp-v2-stable-actions");
}

function syncRowCheckbox(article: HTMLElement, item: NoticeRow, selectedIds: Set<string>, enabled: boolean) {
  article.querySelector<HTMLElement>("[data-pdp-v2-row-select='1']")?.remove();
  if (!enabled) return;
  const holder = document.createElement("label");
  holder.dataset.pdpV2RowSelect = "1";
  holder.dataset.noticeId = item.id;
  holder.className = "pdp-v2-row-select";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = selectedIds.has(item.id);
  input.setAttribute("aria-label", `انتخاب ${normalize(item.title)}`);
  input.onchange = () => window.dispatchEvent(new CustomEvent(ROW_TOGGLE_EVENT, { detail: { id: item.id, checked: input.checked } }));
  holder.appendChild(input);
  article.appendChild(holder);
}

function syncFilterLayout(section: HTMLElement, bulkEnabled: boolean) {
  const filterBar = findFilterBar(section);
  if (!filterBar) return null;
  filterBar.classList.add("pdp-v2-filter-bar");
  Array.from(filterBar.querySelectorAll<HTMLLabelElement>("label")).forEach((label) => label.classList.add("pdp-v2-filter-label"));

  const clearButton = Array.from(filterBar.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent).startsWith("پاک"));
  const clearGroup = clearButton?.parentElement as HTMLElement | null;
  if (clearGroup) {
    clearGroup.classList.add("pdp-v2-clear-group");
    const count = clearGroup.querySelector<HTMLElement>("b");
    if (count) {
      const raw = normalize(count.textContent).replace(/^تعداد ردیف:\s*/, "");
      count.textContent = raw ? `تعداد ردیف: ${raw}` : "تعداد ردیف: ۰";
      count.classList.add("pdp-v2-row-count");
    }
  }

  let host = filterBar.querySelector<HTMLElement>(`#${BULK_HOST_ID}`);
  if (!host) {
    host = document.createElement("div");
    host.id = BULK_HOST_ID;
    filterBar.appendChild(host);
  }
  host.style.display = bulkEnabled ? "block" : "none";

  const oldHost = section.querySelector<HTMLElement>(`#${OLD_BULK_HOST_ID}`) || document.getElementById(OLD_BULK_HOST_ID);
  if (oldHost) oldHost.style.display = "none";
  const oldCompactHost = filterBar.querySelector<HTMLElement>(`#${FILTER_HOST_ID}`);
  oldCompactHost?.querySelectorAll<HTMLElement>(".pdp-compact-bulk-control").forEach((node) => { node.style.display = "none"; });
  return host;
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

function workflowLabel(workflow: ProcurementStableViewState["workflow"]) {
  if (workflow === "recommended") return "پیشنهادی";
  if (workflow === "selected") return "منتخب";
  if (workflow === "submitted") return "ارسال‌شده";
  if (workflow === "results") return "نتایج";
  return "۳ روز اخیر";
}

function bulkButtonLabel(workflow: ProcurementStableViewState["workflow"]) {
  return `حذف گروهی از ${workflowLabel(workflow)}`;
}

function BulkBar({
  workflow,
  pageIds,
  selectedIds,
  busy,
  message,
  onTogglePage,
  onRemove,
}: {
  workflow: ProcurementStableViewState["workflow"];
  pageIds: string[];
  selectedIds: Set<string>;
  busy: boolean;
  message: string;
  onTogglePage: (checked: boolean) => void;
  onRemove: () => void;
}) {
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  return <div className="pdp-v2-bulk-bar" dir="ltr">
    <label className="pdp-v2-select-all" dir="rtl"><input type="checkbox" checked={allSelected} disabled={!pageIds.length || busy} onChange={(event) => onTogglePage(event.target.checked)} />انتخاب همه این صفحه</label>
    <span className="pdp-v2-selected-count" dir="rtl">{selectedIds.size ? `${fa.format(selectedIds.size)} مورد انتخاب شده` : "موردی انتخاب نشده"}</span>
    <button type="button" className="pdp-v2-bulk-remove" dir="rtl" disabled={!selectedIds.size || busy} onClick={onRemove}>{busy ? "در حال حذف..." : bulkButtonLabel(workflow)}</button>
    {message && <small className="pdp-v2-bulk-message" dir="rtl">{message}</small>}
  </div>;
}

export default function ProcurementCardLayoutBulkRemoveV2() {
  const [payload, setPayload] = useState<NoticePayload | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkHost, setBulkHost] = useState<HTMLElement | null>(null);
  const [view, setView] = useState<ProcurementStableViewState>({ top: "dashboard", workflow: "all" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const pageIds = useMemo(() => (payload?.results || []).map((item) => item.id), [payload]);
  const bulkEnabled = stateSupportsBulk(view);

  const togglePage = useCallback((checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => checked ? next.add(id) : next.delete(id));
      return next;
    });
  }, [pageIds]);

  const removeSelected = useCallback(async () => {
    if (!stateSupportsBulk(view) || !selectedIds.size) return;
    const ids = Array.from(selectedIds);
    const label = workflowLabel(view.workflow);
    const confirmation = view.workflow === "selected"
      ? `${fa.format(ids.length)} مورد انتخاب‌شده از «${label}» حذف شوند؟ فقط پرونده‌های قبل از ارسال و بدون سند حذف می‌شوند؛ اصل فراخوان و تحلیل حفظ می‌شود.`
      : view.workflow === "recommended"
        ? `${fa.format(ids.length)} پیشنهاد انتخاب‌شده از فهرست پیشنهادی حذف شوند؟ اصل فراخوان و سابقه تحلیل حذف نمی‌شوند.`
        : `${fa.format(ids.length)} مورد انتخاب‌شده از نمای «${label}» حذف شوند؟ وضعیت کسب‌وکار، اسناد، نتیجه، اصل فراخوان و سابقه تحلیل حفظ می‌شوند.`;
    if (!window.confirm(confirmation)) return;

    setBusy(true);
    setMessage("");
    try {
      const token = await csrfToken();
      const noticeType = view.top === "tenders" ? "tender" : "inquiry";
      const path = view.workflow === "recommended" ? RECOMMENDED_BULK_PATH : WORKFLOW_BULK_PATH;
      const params = new URLSearchParams({ notice_type: noticeType, workflow: view.workflow });
      const reason = view.workflow === "recommended"
        ? "حذف گروهی موارد انتخاب‌شده از فهرست پیشنهادی توسط کاربر"
        : `حذف گروهی موارد انتخاب‌شده از نمای ${label} توسط کاربر`;
      const response = await fetch(`${path}?${params.toString()}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ notice_ids: ids, reason }),
      });
      const result = await response.json() as BulkResponse;
      if (!response.ok) throw new Error(result.detail || "حذف گروهی انجام نشد.");
      const removed = Number(result.dismissed ?? result.removed ?? 0);
      const blocked = Number(result.blocked || 0);
      setMessage(blocked
        ? `${fa.format(removed)} مورد حذف شد؛ ${fa.format(blocked)} مورد محافظت‌شده (مثلاً دارای سند) باقی ماند.`
        : `${fa.format(removed)} مورد از «${label}» حذف شد.`);
      setSelectedIds(new Set());
      const guarded = window as StableWindow;
      guarded.__pdpPaginationPage = 1;
      guarded.__pdpStableListCache?.clear();
      emitProcurementUiSync({ source: "procurement-card-layout-bulk-remove-v2", bulkWorkspace: true, dashboard: true });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "حذف گروهی انجام نشد.");
    } finally {
      setBusy(false);
    }
  }, [selectedIds, view]);

  useEffect(() => {
    const onToggle = (event: Event) => {
      const detail = (event as CustomEvent<{ id?: string; checked?: boolean }>).detail;
      if (!detail?.id) return;
      setSelectedIds((current) => {
        const next = new Set(current);
        if (detail.checked) next.add(detail.id as string);
        else next.delete(detail.id as string);
        return next;
      });
    };
    const onData = (event: Event) => {
      const next = (event as CustomEvent<NoticePayload>).detail || null;
      setPayload(next);
      const valid = new Set((next?.results || []).map((item) => item.id));
      setSelectedIds((current) => new Set(Array.from(current).filter((id) => valid.has(id))));
    };
    const onState = () => {
      setView(getProcurementStableViewState());
      setSelectedIds(new Set());
      setMessage("");
    };
    window.addEventListener(ROW_TOGGLE_EVENT, onToggle);
    window.addEventListener(NOTICE_DATA_EVENT, onData);
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    return () => {
      window.removeEventListener(ROW_TOGGLE_EVENT, onToggle);
      window.removeEventListener(NOTICE_DATA_EVENT, onData);
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    };
  }, []);

  useEffect(() => {
    let frame1 = 0;
    let frame2 = 0;
    const sync = () => {
      frame1 = 0;
      frame2 = 0;
      const state = getProcurementStableViewState();
      setView((current) => current.top === state.top && current.workflow === state.workflow ? current : state);
      const section = currentSection(state);
      if (!section) {
        setBulkHost(null);
        return;
      }
      const enabled = stateSupportsBulk(state);
      const host = syncFilterLayout(section, enabled);
      setBulkHost((current) => current === host ? current : host);
      (payload?.results || []).forEach((item) => {
        const article = findArticle(section, item);
        if (!article) return;
        syncMetadataColumn(article);
        syncRowCheckbox(article, item, selectedIds, enabled);
      });
    };
    const schedule = () => {
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
      frame1 = window.requestAnimationFrame(() => {
        frame2 = window.requestAnimationFrame(sync);
      });
    };
    const onClick = () => schedule();
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
    document.addEventListener("click", onClick, true);
    schedule();
    return () => {
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
      document.removeEventListener("click", onClick, true);
      window.cancelAnimationFrame(frame1);
      window.cancelAnimationFrame(frame2);
    };
  }, [payload, selectedIds]);

  return <>
    <style>{`
      #${OLD_BULK_HOST_ID}{display:none!important}
      .pdp-ux-row-select{display:none!important}
      .pdp-v2-filter-bar{grid-template-columns:minmax(230px,1.55fr) repeat(6,minmax(92px,.72fr)) minmax(138px,.8fr) minmax(355px,1.45fr)!important;gap:6px!important;align-items:end!important}
      .pdp-v2-filter-label{gap:2px!important;font-size:10.5px!important;line-height:1.2!important;min-width:0!important}
      .pdp-v2-filter-label input,.pdp-v2-filter-label select{min-height:32px!important;padding:4px 6px!important;font-size:10.5px!important;line-height:1.2!important}
      .pdp-v2-clear-group{display:flex!important;align-items:end!important;gap:5px!important;min-width:0!important}.pdp-v2-clear-group button{min-height:32px!important;padding:4px 8px!important;font-size:10.5px!important;white-space:nowrap!important}.pdp-v2-row-count{display:inline-flex!important;align-items:center!important;justify-content:center!important;min-height:32px!important;padding:4px 8px!important;border:1px solid #cbd5e1!important;border-radius:999px!important;background:#f8fafc!important;color:#475569!important;font-size:10.5px!important;white-space:nowrap!important;font-weight:700!important}
      #${BULK_HOST_ID}{min-width:0;align-self:end}.pdp-v2-bulk-bar{display:flex;align-items:center;justify-content:flex-start;gap:6px;min-height:32px;flex-wrap:wrap}.pdp-v2-select-all{display:inline-flex;align-items:center;gap:5px;min-height:32px;padding:4px 7px;border:1px solid #cbd5e1;border-radius:9px;background:#fff;color:#334155;font-size:10.5px;font-weight:700;white-space:nowrap}.pdp-v2-select-all input{width:15px;height:15px;margin:0;accent-color:#145563}.pdp-v2-selected-count{display:inline-flex;align-items:center;min-height:32px;padding:4px 7px;border:1px solid #e2e8f0;border-radius:9px;background:#f8fafc;color:#64748b;font-size:10px;white-space:nowrap}.pdp-v2-bulk-remove{min-height:32px;padding:4px 9px;border:1px solid #fecaca;border-radius:9px;background:#fff1f2;color:#be123c;font:inherit;font-size:10.5px;font-weight:700;white-space:nowrap;cursor:pointer}.pdp-v2-bulk-remove:disabled{opacity:.45;cursor:not-allowed}.pdp-v2-bulk-message{flex-basis:100%;color:#0f766e;font-size:10px;font-weight:700;text-align:left}
      .pdp-v2-record{position:relative!important;padding:6px 9px!important;gap:8px!important;grid-template-columns:minmax(0,1fr) minmax(235px,.27fr)!important;min-height:0!important}.pdp-v2-content{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(310px,360px)!important;column-gap:10px!important;row-gap:2px!important;align-items:start!important;min-width:0!important}.pdp-v2-record-top{grid-column:1!important;grid-row:1!important;min-width:0!important}.pdp-v2-record-top>small{display:block!important;min-width:0!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}.pdp-v2-native-status-hidden,.pdp-v2-native-badges-hidden{display:none!important}.pdp-v2-title{grid-column:1!important;grid-row:2!important;display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;-webkit-line-clamp:unset!important;font-size:15px!important;line-height:1.5!important;margin:3px 0 1px!important}.pdp-v2-employer{grid-column:1!important;grid-row:3!important;min-width:0!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;margin:1px 0!important}.pdp-v2-facts{grid-column:1!important;grid-row:4!important;margin-top:3px!important}.pdp-v2-meta{grid-column:2!important;grid-row:1 / span 4!important;display:grid!important;gap:4px!important;align-self:start!important;min-width:0!important;padding-top:1px!important}.pdp-v2-meta-row{display:flex;align-items:center;justify-content:flex-start;gap:4px;flex-wrap:wrap;direction:ltr;min-height:22px}.pdp-v2-meta-row>*{direction:rtl}.pdp-v2-meta-row button{min-height:22px!important;padding:2px 7px!important;font-size:10px!important;border-radius:7px!important}.pdp-v2-meta-row .pdp-compact-source,.pdp-v2-meta-row .pdp-compact-chip{min-height:20px!important;padding:2px 7px!important;font-size:10px!important}
      .pdp-v2-decision{display:grid!important;grid-template-columns:1fr 1fr!important;column-gap:6px!important;row-gap:4px!important;align-content:start!important}.pdp-v2-decision>span,.pdp-v2-decision>dl{grid-column:1/-1!important}.pdp-v2-select-action{grid-column:1!important;grid-row:3!important;margin:0!important;align-self:end!important}.pdp-v2-stable-actions{grid-column:2!important;grid-row:3!important;margin:0!important;align-self:end!important;display:grid!important;gap:4px!important}.pdp-v2-select-action button,.pdp-v2-stable-actions button{width:100%!important;min-height:32px!important;padding:5px 7px!important;font-size:10.5px!important}.pdp-v2-row-select{position:absolute;left:8px;top:8px;z-index:7;display:grid;place-items:center;width:22px;height:22px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;box-shadow:0 2px 6px rgba(15,23,42,.07)}.pdp-v2-row-select input{width:15px;height:15px;margin:0;accent-color:#145563}
      @media(max-width:1450px){.pdp-v2-filter-bar{grid-template-columns:minmax(220px,1.4fr) repeat(6,minmax(88px,.7fr)) minmax(130px,.75fr)!important}#${BULK_HOST_ID}{grid-column:1/-1!important}.pdp-v2-content{grid-template-columns:minmax(0,1fr) minmax(280px,330px)!important}}
      @media(max-width:980px){.pdp-v2-record{grid-template-columns:1fr!important}.pdp-v2-content{grid-template-columns:1fr!important}.pdp-v2-record-top,.pdp-v2-title,.pdp-v2-employer,.pdp-v2-facts,.pdp-v2-meta{grid-column:1!important}.pdp-v2-meta{grid-row:auto!important;margin-top:4px!important}.pdp-v2-decision{border-inline-start:0!important;border-top:1px solid #edf0f2!important;padding-top:7px!important}.pdp-v2-filter-bar{grid-template-columns:repeat(2,minmax(0,1fr))!important}#${BULK_HOST_ID}{grid-column:1/-1!important}}
    `}</style>
    {bulkHost && bulkEnabled ? createPortal(<BulkBar workflow={view.workflow} pageIds={pageIds} selectedIds={selectedIds} busy={busy} message={message} onTogglePage={togglePage} onRemove={() => void removeSelected()} />, bulkHost) : null}
  </>;
}
