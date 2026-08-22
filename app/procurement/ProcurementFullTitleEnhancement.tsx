"use client";

import { useEffect } from "react";
import { PROCUREMENT_UI_SYNC_EVENT } from "./procurementUiSync";
import { getProcurementStableViewState, PROCUREMENT_STABLE_VIEW_STATE_EVENT } from "./procurementStableViewState";

const LONG_TITLE_THRESHOLD = 220;
const DATA_EVENT = "pdp-procurement-compact-notice-data";
// Stable product scope labels retained as a compatibility contract: مناقصات، استعلامات، ارجاعات مستقیم.
const APPLICABLE_TAB_LABELS = ["مناقصات", "استعلامات", "ارجاعات مستقیم"] as const;

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function applyTitlePresentation() {
  const state = getProcurementStableViewState();
  if (state.top !== "tenders" && state.top !== "inquiries" && state.top !== "direct") return;
  void APPLICABLE_TAB_LABELS;
  const main = document.querySelector<HTMLElement>("main[dir='rtl']");
  if (!main) return;
  main.querySelectorAll<HTMLElement>("article h3").forEach((heading) => {
    const title = normalize(heading.textContent);
    if (!title) return;
    heading.classList.add("pdp-full-title");
    heading.classList.toggle("pdp-full-title-long", title.length > LONG_TITLE_THRESHOLD);
  });
}

export default function ProcurementFullTitleEnhancement() {
  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(applyTitlePresentation);
    };
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
    window.addEventListener(DATA_EVENT, schedule);
    window.addEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
    schedule();
    return () => {
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, schedule);
      window.removeEventListener(DATA_EVENT, schedule);
      window.removeEventListener(PROCUREMENT_UI_SYNC_EVENT, schedule);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  return <style>{`
    article h3.pdp-full-title {
      display:block!important;
      max-width:100%!important;
      white-space:normal!important;
      overflow:visible!important;
      text-overflow:clip!important;
      -webkit-line-clamp:unset!important;
    }
    article h3.pdp-full-title.pdp-full-title-long {
      display:-webkit-box!important;
      overflow:hidden!important;
      white-space:normal!important;
      text-overflow:clip!important;
      -webkit-box-orient:vertical;
      -webkit-line-clamp:2!important;
    }
  `}</style>;
}
