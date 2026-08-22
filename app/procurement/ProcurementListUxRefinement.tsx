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
type NoticePayload = { count?: number; results?: NoticeRow[] };
type DirectRow = {
  id: string;
  title: string;
  employer_name: string;
  stage: string;
  stage_label?: string;
};
type DirectPayload = { count?: number; results?: DirectRow[] };
type UxWindow = Window & {
  __pdpPaginationPage?: number;
  __pdpStableListCache?: Map<string, unknown>;
  __pdpCompactDeadlineStatus?: string;
  __pdpCompactPublishedOn?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const BULK_DISMISS_PATH = `${PROCUREMENT_API}/ui/recommendations/dismiss-bulk/`;
const DIRECT_API = `${PROCUREMENT_API}/direct-opportunities`;
const NOTICE_DATA_EVENT = "pdp-procurement-compact-notice-data";
const DIRECT_DATA_EVENT = "pdp-procurement-direct-page-data";
const ROW_SELECT_EVENT = "pdp-procurement-ux-row-select";
const BULK_HOST_ID = "pdp-procurement-ux-bulk-host";
const UX_FILTER_HOST_ID = "pdp-procurement-compact-filter-host";
const MANAGEMENT_TOOLS_HOST_ID = "pdp-procurement-management-toolbar-stable";
const MANAGEMENT_TOOLS_TAB_ATTRIBUTE = "data-pdp-management-tools-tab";
const EXTRACTION_TAB_LABEL = "ابزارهای استخراج و تحلیل";
const SELECTABLE_DIRECT_STAGES = new Set(["new", "reviewing", "following_up", "negotiating"]);
const fa = new Intl.NumberFormat("fa-IR");
const persianCalendar = new Intl.DateTimeFormat("en-US-u-ca-persian", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: "UTC",
});

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeDigits(value: string) {
  const faDigits = "۰۱۲۳۴۵۶۷۸۹";
  const arDigits = "٠١٢٣٤٥٦٧٨٩";
  return value.replace(/[۰-۹٠-٩]/g, (digit) => {
    const faIndex = faDigits.indexOf(digit);
    if (faIndex >= 0) return String(faIndex);
    const arIndex = arDigits.indexOf(digit);
    return arIndex >= 0 ? String(arIndex) : digit;
  });
}

function toFaDigits(value: string) {
  return value.replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)] || digit);
}

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function persianDateParts(date: Date) {
  const parts = persianCalendar.formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value || 0);
  return { year: value("year"), month: value("month"), day: value("day") };
}

function gregorianToJalali(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return "";
  const date = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return "";
  const parts = persianDateParts(date);
  if (!parts.year || !parts.month || !parts.day) return "";
  return toFaDigits(`${parts.year}/${pad2(parts.month)}/${pad2(parts.day)}`);
}

function jalaliToGregorian(value: string) {
  const cleaned = normalizeDigits(value).trim().replace(/[.\-]/g, "/");
  const match = cleaned.match(/^(\d{3,4})\/(\d{1,2})\/(\d{1,2})$/);
  if (!match) return null;
  const jy = Number(match[1]);
  const jm = Number(match[2]);
  const jd = Number(match[3]);
  if (jy < 1200 || jy > 1700 || jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
  const start = Date.UTC(jy + 620, 11, 1, 12);
  const end = Date.UTC(jy + 622, 3, 30, 12);
  for (let timestamp = start; timestamp <= end; timestamp += 86400000) {
    const date = new Date(timestamp);
    const parts = persianDateParts(date);
    if (parts.year === jy && parts.month === jm && parts.day === jd) return date.toISOString().slice(0, 10);
  }
  return null;
}

function setNativeInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  if (setter) setter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function setNativeSelectValue(select: HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
  if (setter) setter.call(select, value);
  else select.value = value;
  select.dispatchEvent(new Event("input", { bubbles: true }));
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function rowKey(title: string, employer: string) {
  return `${normalize(title)}\u0000${normalize(employer)}`;
}

function sourceRank(value: string) {
  const token = normalize(value).toLocaleLowerCase("fa");
  if (token.includes("setad") || token.includes("ستاد")) return 0;
  if (token.includes("hezareh") || token.includes("هزاره")) return 1;
  if (token.includes("parsnamad") || token.includes("پارس")) return 2;
  return 3;
}

function currentSection(state = getProcurementStableViewState()) {
  if (state.top !== "tenders" && state.top !== "inquiries" && state.top !== "direct") return null;
  const expected = stableWorkflowLabel(state);
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
    (candidate) => !candidate.closest("nav") && normalize(candidate.textContent) === expected,
  );
  return button?.closest("section") as HTMLElement | null;
}

function findArticle(section: HTMLElement, id: string, title: string, employer: string) {
  const identified = Array.from(section.querySelectorAll<HTMLElement>("article[data-pdp-notice-id]")).find(
    (article) => article.dataset.pdpNoticeId === id,
  );
  if (identified) return identified;
  const key = rowKey(title, employer);
  return Array.from(section.querySelectorAll<HTMLElement>("article")).find((article) => {
    const heading = normalize(article.querySelector("h3")?.textContent);
    const paragraph = normalize(article.querySelector("p")?.textContent);
    return rowKey(heading, paragraph) === key || (heading.length > 12 && normalize(title).startsWith(heading.replace(/…$/, "")));
  }) || null;
}

function findFilterBar(section: HTMLElement) {
  const searchLabel = Array.from(section.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("جست‌وجو"));
  return searchLabel?.parentElement as HTMLElement | null;
}

function clearStableListCache() {
  const guarded = window as UxWindow;
  guarded.__pdpPaginationPage = 1;
  guarded.__pdpStableListCache?.clear();
}

function setAddedFilterGlobals(deadlineStatus: string, publishedOn: string) {
  const guarded = window as UxWindow;
  guarded.__pdpCompactDeadlineStatus = deadlineStatus;
  guarded.__pdpCompactPublishedOn = publishedOn;
  clearStableListCache();
}

function enhanceJalaliPublicationFilter(section: HTMLElement) {
  const filterBar = findFilterBar(section);
  if (!filterBar) return;
  const labels = Array.from(filterBar.querySelectorAll<HTMLLabelElement>("label"));
  const dateLabel = labels.find((label) => normalize(label.textContent).startsWith("تاریخ انتشار"));
  const nativeDate = dateLabel?.querySelector<HTMLInputElement>('input[type="date"]');
  if (dateLabel && nativeDate) {
    nativeDate.classList.add("pdp-ux-native-date");
    let jalali = dateLabel.querySelector<HTMLInputElement>("input.pdp-ux-jalali-date");
    if (!jalali) {
      jalali = document.createElement("input");
      jalali.type = "text";
      jalali.inputMode = "numeric";
      jalali.autocomplete = "off";
      jalali.className = "pdp-ux-jalali-date";
      jalali.placeholder = "۱۴۰۵/۰۵/۲۹";
      jalali.setAttribute("aria-label", "تاریخ انتشار شمسی");
      jalali.dir = "ltr";
      jalali.onchange = () => {
        const next = jalaliToGregorian(jalali?.value || "");
        if (!jalali) return;
        if (!jalali.value.trim()) {
          jalali.removeAttribute("aria-invalid");
          setNativeInputValue(nativeDate, "");
          setAddedFilterGlobals((window as UxWindow).__pdpCompactDeadlineStatus || "", "");
          emitProcurementUiSync({ source: "procurement-list-ux", bulkWorkspace: true });
          return;
        }
        if (!next) {
          jalali.setAttribute("aria-invalid", "true");
          jalali.title = "تاریخ را به صورت شمسی، مانند ۱۴۰۵/۰۵/۲۹، وارد کنید.";
          return;
        }
        jalali.removeAttribute("aria-invalid");
        jalali.title = "";
        setNativeInputValue(nativeDate, next);
        setAddedFilterGlobals((window as UxWindow).__pdpCompactDeadlineStatus || "", next);
        emitProcurementUiSync({ source: "procurement-list-ux", bulkWorkspace: true });
      };
      jalali.onkeydown = (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          jalali?.blur();
        }
      };
      dateLabel.appendChild(jalali);
    }
    const current = (window as UxWindow).__pdpCompactPublishedOn || nativeDate.value;
    if (document.activeElement !== jalali) jalali.value = current ? gregorianToJalali(current) : "";
  }

  const compactHost = filterBar.querySelector<HTMLElement>(`#${UX_FILTER_HOST_ID}`) || document.getElementById(UX_FILTER_HOST_ID);
  const clearButton = Array.from(filterBar.querySelectorAll<HTMLButtonElement>("button")).find((button) => normalize(button.textContent).startsWith("پاک"));
  const clearContainer = clearButton?.parentElement;
  if (compactHost && clearContainer && compactHost.parentElement === filterBar && compactHost.nextElementSibling !== clearContainer) {
    filterBar.insertBefore(compactHost, clearContainer);
  }
  if (clearButton && !clearButton.dataset.pdpUxClearInstalled) {
    clearButton.dataset.pdpUxClearInstalled = "1";
    clearButton.addEventListener("click", () => {
      window.requestAnimationFrame(() => {
        const deadlineLabel = Array.from(filterBar.querySelectorAll<HTMLLabelElement>("label")).find((label) => normalize(label.textContent).startsWith("وضعیت مهلت"));
        const deadlineSelect = deadlineLabel?.querySelector<HTMLSelectElement>("select");
        const native = dateLabel?.querySelector<HTMLInputElement>('input[type="date"]');
        const visible = dateLabel?.querySelector<HTMLInputElement>("input.pdp-ux-jalali-date");
        if (deadlineSelect) setNativeSelectValue(deadlineSelect, "");
        if (native) setNativeInputValue(native, "");
        if (visible) {
          visible.value = "";
          visible.removeAttribute("aria-invalid");
        }
        setAddedFilterGlobals("", "");
        emitProcurementUiSync({ source: "procurement-list-ux", bulkWorkspace: true });
      });
    });
  }
}

function ensureBulkHost(section: HTMLElement, visible: boolean) {
  const filterBar = findFilterBar(section);
  if (!filterBar) return null;
  let host = document.getElementById(BULK_HOST_ID) as HTMLElement | null;
  if (!host) {
    host = document.createElement("div");
    host.id = BULK_HOST_ID;
  }
  if (host.parentElement !== section) section.insertBefore(host, filterBar);
  host.style.display = visible ? "block" : "none";
  return host;
}

function removeBulkHostWhenNotApplicable() {
  const host = document.getElementById(BULK_HOST_ID) as HTMLElement | null;
  if (host) host.style.display = "none";
}

function suppressDirectRecommendedTab(section: HTMLElement) {
  Array.from(section.querySelectorAll<HTMLButtonElement>("button")).forEach((button) => {
    if (normalize(button.textContent) === "پیشنهادی" && !button.closest("article")) button.style.display = "none";
  });
}

function syncManagementToolsActiveState() {
  const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
  const nav = root?.querySelector("nav");
  if (!nav) return;
  const toolsButton = nav.querySelector<HTMLButtonElement>(`button[${MANAGEMENT_TOOLS_TAB_ATTRIBUTE}]`);
  const toolsHost = document.getElementById(MANAGEMENT_TOOLS_HOST_ID) as HTMLElement | null;
  const toolsActive = Boolean(toolsHost && toolsHost.style.display !== "none");
  const nativeButtons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button")).filter((button) => button !== toolsButton);
  if (toolsButton) {
    toolsButton.style.background = toolsActive ? "#145563" : "";
    toolsButton.style.color = toolsActive ? "#fff" : "";
    toolsButton.style.fontWeight = toolsActive ? "700" : "";
  }
  nativeButtons.forEach((button) => {
    if (toolsActive) {
      button.style.background = "transparent";
      button.style.color = "#48545b";
    } else {
      button.style.removeProperty("background");
      button.style.removeProperty("color");
    }
    if (normalize(button.textContent) === EXTRACTION_TAB_LABEL && toolsActive) button.setAttribute("aria-selected", "false");
  });
  if (toolsButton) toolsButton.setAttribute("aria-selected", toolsActive ? "true" : "false");
}

function syncTitleWidth(section: HTMLElement) {
  section.querySelectorAll<HTMLElement>("article h3").forEach((heading) => {
    const title = normalize(heading.textContent);
    if (!title) return;
    heading.classList.add("pdp-ux-title");
    heading.classList.toggle("pdp-ux-title-long", title.length > 320);
    if (title.length <= 320) heading.classList.remove("pdp-full-title-long");
  });
}

function syncNoticeRows(section: HTMLElement, payload: NoticePayload | null, selectedIds: Set<string>, showSelection: boolean) {
  if (!payload?.results) return;
  const visibleIds = new Set(payload.results.map((item) => item.id));
  section.querySelectorAll<HTMLElement>("[data-pdp-ux-row-select]").forEach((node) => {
    const id = node.dataset.noticeId || "";
    if (!showSelection || !visibleIds.has(id)) node.remove();
  });

  payload.results.forEach((item) => {
    const article = findArticle(section, item.id, item.title, item.employer_name);
    if (!article) return;
    article.classList.add("pdp-ux-record");
    const content = article.children.item(0) as HTMLElement | null;
    const heading = article.querySelector<HTMLElement>("h3");
    const recordTop = content?.firstElementChild as HTMLElement | null;
    const statusZone = recordTop?.lastElementChild as HTMLElement | null;
    if (statusZone) statusZone.classList.add("pdp-ux-status-zone");

    if (recordTop) {
      Array.from(recordTop.querySelectorAll<HTMLAnchorElement>("a")).forEach((anchor) => {
        if (!anchor.classList.contains("pdp-compact-source")) {
          anchor.classList.add("pdp-ux-native-source");
          anchor.style.display = "none";
        }
      });
    }

    const badgeGroup = article.querySelector<HTMLElement>("[data-pdp-compact-badges='1']");
    if (badgeGroup) {
      badgeGroup.classList.add("pdp-ux-badge-layout");
      let sourceStrip = badgeGroup.querySelector<HTMLElement>(".pdp-ux-source-strip");
      if (!sourceStrip) {
        sourceStrip = document.createElement("div");
        sourceStrip.className = "pdp-ux-source-strip";
        badgeGroup.prepend(sourceStrip);
      }
      let infoStrip = badgeGroup.querySelector<HTMLElement>(".pdp-ux-info-strip");
      if (!infoStrip) {
        infoStrip = document.createElement("div");
        infoStrip.className = "pdp-ux-info-strip";
        badgeGroup.appendChild(infoStrip);
      }
      const sources = Array.from(badgeGroup.querySelectorAll<HTMLAnchorElement>("a.pdp-compact-source"));
      sources.sort((a, b) => sourceRank(a.textContent || "") - sourceRank(b.textContent || "") || normalize(a.textContent).localeCompare(normalize(b.textContent), "fa"));
      sources.forEach((source) => sourceStrip?.appendChild(source));
      Array.from(badgeGroup.querySelectorAll<HTMLElement>(".pdp-compact-chip")).forEach((chip) => {
        if (chip.classList.contains("pdp-source-count")) {
          chip.style.display = "none";
          return;
        }
        infoStrip?.appendChild(chip);
      });
      if (statusZone && badgeGroup.parentElement !== statusZone) statusZone.appendChild(badgeGroup);
    }

    if (content) {
      Array.from(content.querySelectorAll<HTMLElement>("span")).forEach((node) => {
        if (node.closest("[data-pdp-compact-badges='1']")) return;
        const text = normalize(node.textContent);
        if (!text) return;
        if ((item.province && text === normalize(item.province)) || text.startsWith("پردازش:") || text.includes("باقی‌مانده") || /ساعت گذشته|روز گذشته/.test(text)) {
          node.classList.add("pdp-ux-duplicate-fact");
          node.style.display = "none";
        }
      });
    }

    if (heading) {
      const title = normalize(item.title || heading.textContent);
      heading.classList.add("pdp-ux-title");
      heading.classList.toggle("pdp-ux-title-long", title.length > 320);
      if (title.length <= 320) heading.classList.remove("pdp-full-title-long");
    }

    if (showSelection) {
      let holder = article.querySelector<HTMLElement>("[data-pdp-ux-row-select]");
      if (!holder) {
        holder = document.createElement("label");
        holder.setAttribute("data-pdp-ux-row-select", "1");
        holder.dataset.noticeId = item.id;
        holder.className = "pdp-ux-row-select";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.setAttribute("aria-label", `انتخاب ${normalize(item.title)}`);
        input.onchange = () => window.dispatchEvent(new CustomEvent(ROW_SELECT_EVENT, { detail: { id: item.id, checked: input.checked } }));
        holder.appendChild(input);
        article.appendChild(holder);
      }
      const input = holder.querySelector<HTMLInputElement>('input[type="checkbox"]');
      if (input) input.checked = selectedIds.has(item.id);
    }
  });
}

async function csrfToken() {
  const response = await fetch(`${API_BASE}/auth/session/`, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("نشست کاربری در دسترس نیست.");
  const payload = await response.json() as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

async function updateDirectToSelected(item: DirectRow, button: HTMLButtonElement) {
  if (!SELECTABLE_DIRECT_STAGES.has(item.stage)) return;
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "در حال ثبت...";
  try {
    const token = await csrfToken();
    const response = await fetch(`${DIRECT_API}/${item.id}/`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
      body: JSON.stringify({ stage: "selected" }),
    });
    if (!response.ok) throw new Error("انتخاب ارجاع مستقیم انجام نشد.");
    clearStableListCache();
    emitProcurementUiSync({ source: "procurement-list-ux", directId: item.id, dashboard: true, bulkWorkspace: true });
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "انتخاب ارجاع مستقیم انجام نشد.");
    button.disabled = false;
    button.textContent = original;
  }
}

function syncDirectRows(section: HTMLElement, rows: DirectRow[]) {
  const byId = new Map(rows.map((item) => [item.id, item]));
  const byKey = new Map(rows.map((item) => [rowKey(item.title, item.employer_name), item]));
  Array.from(section.querySelectorAll<HTMLElement>("article")).forEach((article) => {
    const heading = normalize(article.querySelector("h3")?.textContent);
    const employer = normalize(article.querySelector("p")?.textContent);
    const item = (article.dataset.pdpDirectId && byId.get(article.dataset.pdpDirectId)) || byKey.get(rowKey(heading, employer));
    if (!item) return;
    article.classList.add("pdp-ux-record");
    const decision = article.children.item(1) as HTMLElement | null;
    if (!decision) return;
    let host = decision.querySelector<HTMLElement>("[data-pdp-ux-direct-action]");
    if (!host) {
      host = document.createElement("div");
      host.setAttribute("data-pdp-ux-direct-action", "1");
      host.className = "pdp-ux-direct-action";
      decision.appendChild(host);
    }
    host.replaceChildren();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pdp-ux-action-button";
    const selectable = SELECTABLE_DIRECT_STAGES.has(item.stage);
    button.textContent = selectable ? "انتخاب" : (item.stage_label || "وضعیت ثبت‌شده");
    button.disabled = !selectable;
    if (selectable) button.onclick = () => void updateDirectToSelected(item, button);
    host.appendChild(button);
  });
}

function BulkSelectionBar({
  pageIds,
  selectedIds,
  onTogglePage,
  onDismiss,
  busy,
  message,
}: {
  pageIds: string[];
  selectedIds: Set<string>;
  onTogglePage: (checked: boolean) => void;
  onDismiss: () => void;
  busy: boolean;
  message: string;
}) {
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  return <div className="pdp-ux-bulk-bar" dir="rtl">
    <label className="pdp-ux-select-all"><input type="checkbox" checked={allSelected} disabled={!pageIds.length || busy} onChange={(event) => onTogglePage(event.target.checked)} />انتخاب همه این صفحه</label>
    <span className="pdp-ux-selected-count">{selectedIds.size ? `${fa.format(selectedIds.size)} مورد انتخاب شده` : "موردی انتخاب نشده"}</span>
    <button type="button" className="pdp-ux-bulk-dismiss" disabled={!selectedIds.size || busy} onClick={onDismiss}>{busy ? "در حال حذف..." : "حذف گروهی از پیشنهادی"}</button>
    {message && <small className="pdp-ux-bulk-message">{message}</small>}
  </div>;
}

export default function ProcurementListUxRefinement() {
  const [noticePayload, setNoticePayload] = useState<NoticePayload | null>(null);
  const [directPayload, setDirectPayload] = useState<DirectPayload | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkHost, setBulkHost] = useState<HTMLElement | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMessage, setBulkMessage] = useState("");

  const pageIds = useMemo(() => (noticePayload?.results || []).map((item) => item.id), [noticePayload]);

  const togglePage = useCallback((checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => checked ? next.add(id) : next.delete(id));
      return next;
    });
  }, [pageIds]);

  const dismissSelected = useCallback(async () => {
    const state = getProcurementStableViewState();
    if ((state.top !== "tenders" && state.top !== "inquiries") || state.workflow !== "recommended" || !selectedIds.size) return;
    const ids = Array.from(selectedIds);
    if (!window.confirm(`${fa.format(ids.length)} پیشنهاد انتخاب‌شده از فهرست پیشنهادی حذف شوند؟ خود فراخوان‌ها و سابقه تحلیل حذف نمی‌شوند.`)) return;
    setBulkBusy(true);
    setBulkMessage("");
    try {
      const token = await csrfToken();
      const params = new URLSearchParams({ notice_type: state.top === "tenders" ? "tender" : "inquiry", workflow: "recommended" });
      const response = await fetch(`${BULK_DISMISS_PATH}?${params.toString()}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token, Accept: "application/json" },
        body: JSON.stringify({ notice_ids: ids, reason: "حذف گروهی موارد انتخاب‌شده از فهرست پیشنهادی توسط کاربر" }),
      });
      const payload = await response.json() as { dismissed?: number; detail?: string };
      if (!response.ok) throw new Error(payload.detail || "حذف گروهی پیشنهادها انجام نشد.");
      setBulkMessage(`${fa.format(payload.dismissed || ids.length)} پیشنهاد از فهرست پیشنهادی حذف شد.`);
      setSelectedIds(new Set());
      clearStableListCache();
      emitProcurementUiSync({ source: "procurement-list-ux", bulkWorkspace: true, dashboard: true });
    } catch (error) {
      setBulkMessage(error instanceof Error ? error.message : "حذف گروهی پیشنهادها انجام نشد.");
    } finally {
      setBulkBusy(false);
    }
  }, [selectedIds]);

  useEffect(() => {
    const onSelect = (event: Event) => {
      const detail = (event as CustomEvent<{ id?: string; checked?: boolean }>).detail;
      if (!detail?.id) return;
      setSelectedIds((current) => {
        const next = new Set(current);
        if (detail.checked) next.add(detail.id as string);
        else next.delete(detail.id as string);
        return next;
      });
    };
    const onNoticeData = (event: Event) => {
      const payload = (event as CustomEvent<NoticePayload>).detail || null;
      setNoticePayload(payload);
      const valid = new Set((payload?.results || []).map((item) => item.id));
      setSelectedIds((current) => new Set(Array.from(current).filter((id) => valid.has(id))));
    };
    const onDirectData = (event: Event) => setDirectPayload((event as CustomEvent<DirectPayload>).detail || null);
    const onState = () => {
      setSelectedIds(new Set());
      setBulkMessage("");
    };
    window.addEventListener(ROW_SELECT_EVENT, onSelect);
    window.addEventListener(NOTICE_DATA_EVENT, onNoticeData);
    window.addEventListener(DIRECT_DATA_EVENT, onDirectData);
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    return () => {
      window.removeEventListener(ROW_SELECT_EVENT, onSelect);
      window.removeEventListener(NOTICE_DATA_EVENT, onNoticeData);
      window.removeEventListener(DIRECT_DATA_EVENT, onDirectData);
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    };
  }, []);

  useEffect(() => {
    let frame = 0;
    let secondFrame = 0;
    const sync = () => {
      frame = 0;
      secondFrame = 0;
      const state = getProcurementStableViewState();
      syncManagementToolsActiveState();
      const section = currentSection(state);
      if (!section) {
        removeBulkHostWhenNotApplicable();
        setBulkHost(null);
        return;
      }
      syncTitleWidth(section);
      if (state.top === "tenders" || state.top === "inquiries") {
        enhanceJalaliPublicationFilter(section);
        const showBulk = state.workflow === "recommended";
        const host = ensureBulkHost(section, showBulk);
        setBulkHost((current) => current === host ? current : host);
        syncNoticeRows(section, noticePayload, selectedIds, showBulk);
      } else {
        removeBulkHostWhenNotApplicable();
        setBulkHost(null);
      }
      if (state.top === "direct") {
        suppressDirectRecommendedTab(section);
        if (state.workflow === "all") syncDirectRows(section, directPayload?.results || []);
        else section.querySelectorAll("[data-pdp-ux-direct-action]").forEach((node) => node.remove());
      }
    };
    const schedule = () => {
      window.cancelAnimationFrame(frame);
      window.cancelAnimationFrame(secondFrame);
      frame = window.requestAnimationFrame(() => {
        secondFrame = window.requestAnimationFrame(sync);
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
      window.cancelAnimationFrame(frame);
      window.cancelAnimationFrame(secondFrame);
    };
  }, [noticePayload, directPayload, selectedIds]);

  const state = typeof window === "undefined" ? ({ top: "dashboard", workflow: "all" } as ProcurementStableViewState) : getProcurementStableViewState();
  const showBulk = (state.top === "tenders" || state.top === "inquiries") && state.workflow === "recommended";

  return <>
    <style>{`
      #pdp-procurement-compact-filter-host .pdp-compact-bulk-control{display:none!important}
      .pdp-ux-native-date{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important}
      .pdp-ux-jalali-date{width:100%;min-height:34px;border:1px solid rgba(15,23,42,.16);border-radius:8px;padding:5px 7px;background:white;font:inherit;text-align:center}
      .pdp-ux-jalali-date[aria-invalid="true"]{border-color:#ef4444;background:#fff7f7}
      #${BULK_HOST_ID}{margin:0 0 8px}
      .pdp-ux-bulk-bar{display:flex;align-items:center;justify-content:flex-start;gap:9px;flex-wrap:wrap;padding:7px 9px;border:1px solid #e2e8f0;border-radius:11px;background:#fff}
      .pdp-ux-select-all{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:#334155}.pdp-ux-select-all input{width:16px;height:16px;accent-color:#145563}
      .pdp-ux-selected-count{font-size:10.5px;color:#64748b}.pdp-ux-bulk-dismiss{min-height:32px;border:1px solid #fecaca;border-radius:8px;background:#fff1f2;color:#be123c;padding:5px 10px;font:inherit;font-size:11px;font-weight:700;cursor:pointer}.pdp-ux-bulk-dismiss:disabled{opacity:.45;cursor:not-allowed}.pdp-ux-bulk-message{flex-basis:100%;color:#0f766e;font-weight:700;font-size:10.5px}
      .pdp-ux-record{position:relative!important;padding:6px 9px!important;gap:7px!important;grid-template-columns:minmax(0,1fr) minmax(210px,.28fr)!important}
      .pdp-ux-record>div:last-child{display:grid!important;grid-template-columns:1fr 1fr!important;column-gap:6px!important;row-gap:4px!important;align-content:start!important;padding-inline-start:8px!important}
      .pdp-ux-record>div:last-child>span,.pdp-ux-record>div:last-child>dl{grid-column:1/-1!important}.pdp-ux-record>div:last-child>div{margin:0!important;align-self:end!important}.pdp-ux-record>div:last-child>div button{width:100%!important;min-height:32px!important;padding:5px 7px!important;font-size:10.5px!important}
      .pdp-ux-row-select{position:absolute;left:9px;top:8px;z-index:4;display:grid;place-items:center;width:22px;height:22px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;box-shadow:0 2px 6px rgba(15,23,42,.06)}.pdp-ux-row-select input{width:15px;height:15px;margin:0;accent-color:#145563}
      .pdp-ux-status-zone{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:4px!important;flex-wrap:wrap!important;max-width:100%!important}.pdp-ux-status-zone>.pdp-ux-badge-layout{flex:1 0 100%!important;width:100%!important}
      .pdp-ux-badge-layout{display:grid!important;gap:3px!important;margin:2px 0 0!important}.pdp-ux-source-strip{direction:ltr;display:flex;align-items:center;justify-content:flex-start;gap:4px;flex-wrap:wrap}.pdp-ux-source-strip .pdp-compact-source{direction:rtl}.pdp-ux-source-strip .pdp-compact-source::after{content:"↗";font-size:9px;margin-inline-start:4px;opacity:.7}.pdp-ux-info-strip{display:flex;align-items:center;justify-content:flex-start;gap:4px;flex-wrap:wrap}
      .pdp-ux-native-source,.pdp-ux-duplicate-fact,.pdp-source-count{display:none!important}
      article h3.pdp-ux-title{display:block!important;max-width:100%!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;-webkit-line-clamp:unset!important;font-size:15px!important;line-height:1.5!important;margin:2px 0 1px!important}
      article h3.pdp-ux-title.pdp-ux-title-long{display:-webkit-box!important;overflow:hidden!important;-webkit-box-orient:vertical!important;-webkit-line-clamp:2!important}
      .pdp-ux-direct-action{display:grid;grid-column:1/-1}.pdp-ux-action-button{min-height:32px;border:0;border-radius:8px;background:#145563;color:white;padding:5px 8px;font:inherit;font-size:10.5px;font-weight:700;cursor:pointer}.pdp-ux-action-button:disabled{background:#f1f5f9;color:#64748b;border:1px solid #dbe3ec;cursor:not-allowed}
      @media(max-width:900px){.pdp-ux-record{grid-template-columns:1fr!important}.pdp-ux-record>div:last-child{border-inline-start:0!important;border-top:1px solid #edf0f2!important;padding-inline-start:0!important;padding-top:7px!important}}
    `}</style>
    {bulkHost && showBulk ? createPortal(<BulkSelectionBar pageIds={pageIds} selectedIds={selectedIds} onTogglePage={togglePage} onDismiss={() => void dismissSelected()} busy={bulkBusy} message={bulkMessage} />, bulkHost) : null}
  </>;
}
