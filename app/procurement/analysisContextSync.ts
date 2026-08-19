export const ANALYSIS_CONTEXT_SYNC_EVENT = "pdp-analysis-context-sync";

export type AnalysisContextSyncKind = "active" | "draft" | "refresh";

export type AnalysisContextSyncDetail<T = unknown> = {
  kind: AnalysisContextSyncKind;
  snapshot?: T;
  source?: string;
};

export function emitAnalysisContextSync<T = unknown>(detail: AnalysisContextSyncDetail<T>) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<AnalysisContextSyncDetail<T>>(ANALYSIS_CONTEXT_SYNC_EVENT, { detail }));
}
