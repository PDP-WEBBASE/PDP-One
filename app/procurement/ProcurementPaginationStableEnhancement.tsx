"use client";

/**
 * Presentation compatibility boundary only.
 *
 * ProcurementWorkspaceV13 owns list page/page-size state and renders the canonical
 * pagination controls. Older versions of this enhancement replaced window.fetch,
 * inferred active view/filter state from DOM/global window fields, rewrote list
 * requests and dispatched secondary data events. That created a second Data Owner
 * and violated the Session #136 Single Data Owner / no-global-fetch rules.
 *
 * Keep the mounted component as a stable composition placeholder so the approved
 * Session #122 visual composition does not change, but it must not own requests,
 * navigation, filters, cache or pagination state.
 */
export default function ProcurementPaginationStableEnhancement() {
  return null;
}
