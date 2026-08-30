export type ProcurementStableTop = "dashboard" | "tenders" | "inquiries" | "direct" | "management";
export type ProcurementStableWorkflow = "all" | "recommended" | "selected" | "submitted" | "results";

export type ProcurementStableViewState = {
  top: ProcurementStableTop;
  workflow: ProcurementStableWorkflow;
};

export const PROCUREMENT_STABLE_VIEW_STATE_EVENT = "pdp-procurement-stable-view-state";

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

function defaultState(): ProcurementStableViewState {
  return { top: "dashboard", workflow: "all" };
}

// Read-only projection of the canonical React workspace state. This module is not
// an independent navigation owner and never infers state from DOM text/clicks.
let currentState: ProcurementStableViewState = defaultState();

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

/**
 * Publish a projection from the canonical ProcurementWorkspace React state.
 * Only the canonical owner should call this function.
 */
export function setProcurementStableViewState(next: ProcurementStableViewState) {
  if (currentState.top === next.top && currentState.workflow === next.workflow) return;
  currentState = { ...next };
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ProcurementStableViewState>(PROCUREMENT_STABLE_VIEW_STATE_EVENT, { detail: { ...next } }));
  }
}

/**
 * Historical compatibility no-op.
 *
 * Session #122 used a capture-phase document click listener to infer application
 * state from Persian button labels. That created a second navigation owner beside
 * ProcurementWorkspace React state. Keep the export for old callers, but never
 * install DOM-driven state mutation again.
 */
export function installProcurementStableViewState() {
  return;
}

export function procurementStableViewContextKey() {
  const state = getProcurementStableViewState();
  return `${state.top}:${state.workflow}`;
}
