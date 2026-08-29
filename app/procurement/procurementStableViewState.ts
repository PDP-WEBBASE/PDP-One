export type ProcurementStableTop = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
export type ProcurementStableWorkflow = "all" | "recommended" | "selected" | "submitted" | "results";

export type ProcurementStableViewState = {
  top: ProcurementStableTop;
  workflow: ProcurementStableWorkflow;
};

export const PROCUREMENT_STABLE_VIEW_STATE_EVENT = "pdp-procurement-stable-view-state";

const TOP_BY_LABEL = new Map<string, ProcurementStableTop>([
  ["داشبورد مدیریتی", "dashboard"],
  ["مناقصات", "tenders"],
  ["استعلامات", "inquiries"],
  ["ارجاعات مستقیم", "direct"],
  ["مدیریت زیرسامانه", "management"],
]);

const WORKFLOW_BY_LABEL = new Map<string, ProcurementStableWorkflow>([
  ["مناقصات ۳ روز اخیر", "all"],
  ["استعلامات ۳ روز اخیر", "all"],
  ["مناقصات اخیر", "all"],
  ["استعلامات اخیر", "all"],
  ["کل ارجاعات مستقیم", "all"],
  ["ارجاعات مستقیم اخیر", "all"],
  ["پیشنهادی", "recommended"],
  ["منتخب", "selected"],
  ["ارسال‌شده", "submitted"],
  ["نتایج", "results"],
]);

const TOP_LABELS: Record<ProcurementStableTop, string> = {
  dashboard: "داشبورد مدیریتی",
  tenders: "مناقصات",
  inquiries: "استعلامات",
  direct: "ارجاعات مستقیم",
  management: "مدیریت زیرسامانه",
};

const WORKFLOW_LABELS: Record<ProcurementStableWorkflow, string> = {
  all: "",
  recommended: "پیشنهادی",
  selected: "منتخب",
  submitted: "ارسال‌شده",
  results: "نتایج",
};

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function defaultState(): ProcurementStableViewState {
  return { top: "dashboard", workflow: "all" };
}

let currentState: ProcurementStableViewState = defaultState();
let legacyInstallerActive = false;

export function getProcurementStableViewState(): ProcurementStableViewState {
  return { ...currentState };
}

export function stableTopLabel(top = getProcurementStableViewState().top) {
  return TOP_LABELS[top];
}

export function stableWorkflowLabel(state = getProcurementStableViewState()) {
  if (state.workflow !== "all") return WORKFLOW_LABELS[state.workflow];
  if (state.top === "tenders") return "مناقصات اخیر";
  if (state.top === "inquiries") return "استعلامات اخیر";
  if (state.top === "direct") return "ارجاعات مستقیم اخیر";
  return "";
}

export function setProcurementStableViewState(next: ProcurementStableViewState) {
  if (currentState.top === next.top && currentState.workflow === next.workflow) return;
  currentState = { ...next };
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ProcurementStableViewState>(PROCUREMENT_STABLE_VIEW_STATE_EVENT, { detail: { ...next } }));
  }
}

/**
 * Historical compatibility only. New workspace code publishes explicit React state
 * through setProcurementStableViewState and must not depend on DOM label inference.
 */
export function installProcurementStableViewState() {
  if (typeof document === "undefined" || legacyInstallerActive) return;
  legacyInstallerActive = true;
  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button") : null;
    if (!button) return;
    const label = normalize(button.textContent);
    const top = TOP_BY_LABEL.get(label);
    if (top) {
      setProcurementStableViewState({ top, workflow: "all" });
      return;
    }
    const workflow = WORKFLOW_BY_LABEL.get(label);
    if (!workflow) return;
    if (!["tenders", "inquiries", "direct"].includes(currentState.top)) return;
    setProcurementStableViewState({ ...currentState, workflow });
  }, true);
}

export function procurementStableViewContextKey() {
  const state = getProcurementStableViewState();
  return `${state.top}:${state.workflow}`;
}
