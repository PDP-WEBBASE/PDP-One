export type DirectWorkflowView = "all" | "recommended" | "selected" | "submitted" | "results";

/**
 * Canonical API projection for Direct Referrals.
 * The user-facing "ارجاعات مستقیم اخیر" entry is the unfiltered, recency-ordered
 * list. Recommended remains an explicit semantic only when a caller asks for it.
 */
export function directWorkflowQuery(view: DirectWorkflowView) {
  return view === "all" ? "" : view;
}
