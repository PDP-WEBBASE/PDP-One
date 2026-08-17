"use client";

export const PROCUREMENT_UI_SYNC_EVENT = "pdp-procurement-ui-sync";

export type ProcurementUiSyncDetail = {
  source: string;
  noticeId?: string;
  directId?: string;
  dashboard?: boolean;
  bulkWorkspace?: boolean;
  management?: boolean;
  closeSubmissionDialog?: boolean;
};

export function emitProcurementUiSync(detail: ProcurementUiSyncDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<ProcurementUiSyncDetail>(PROCUREMENT_UI_SYNC_EVENT, { detail }));
}
