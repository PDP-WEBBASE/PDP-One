"use client";

import { useEffect, useRef, useState } from "react";
import {
  PROCUREMENT_NOTICE_CONTEXT_LIFECYCLE_EVENT,
  type ProcurementNoticeContextLifecycleDetail,
} from "./procurementDataClient";

type PendingState = {
  key: string;
  noticeType: "tender" | "inquiry";
  phase: "loading" | "error";
} | null;

export default function ProcurementNoticeContextRenderGuard() {
  const pendingKey = useRef("");
  const [pending, setPending] = useState<PendingState>(null);

  useEffect(() => {
    let revealFrame = 0;

    const onLifecycle = (event: Event) => {
      const detail = (event as CustomEvent<ProcurementNoticeContextLifecycleDetail>).detail;
      if (!detail?.key) return;

      if (detail.phase === "cold-start") {
        if (revealFrame) cancelAnimationFrame(revealFrame);
        pendingKey.current = detail.key;
        setPending({ key: detail.key, noticeType: detail.noticeType, phase: "loading" });
        return;
      }

      if (detail.phase === "cache-hit") {
        // A cache hit belongs to the currently requested context and is intentionally
        // renderable immediately. It supersedes any guard left by an older cold/aborted
        // context while the same-context background revalidation continues independently.
        if (revealFrame) cancelAnimationFrame(revealFrame);
        pendingKey.current = "";
        setPending(null);
        return;
      }

      if (detail.key !== pendingKey.current) return;

      if (detail.phase === "success") {
        // The workspace commits the payload in the promise continuation immediately after
        // the data client settles. Reveal on the next frame so the new context is painted
        // before the previous context becomes visible again.
        revealFrame = requestAnimationFrame(() => {
          if (pendingKey.current !== detail.key) return;
          pendingKey.current = "";
          setPending(null);
        });
        return;
      }

      if (detail.phase === "error") {
        setPending({ key: detail.key, noticeType: detail.noticeType, phase: "error" });
        return;
      }

      // An aborted request normally means navigation moved to a newer context. Keep the
      // previous context hidden until that newer context emits cold-start/cache-hit and then
      // success/error according to its own cache/network state.
    };

    window.addEventListener(PROCUREMENT_NOTICE_CONTEXT_LIFECYCLE_EVENT, onLifecycle);
    return () => {
      if (revealFrame) cancelAnimationFrame(revealFrame);
      window.removeEventListener(PROCUREMENT_NOTICE_CONTEXT_LIFECYCLE_EVENT, onLifecycle);
    };
  }, []);

  if (!pending) return null;

  const layout = pending.noticeType === "tender" ? "tenders" : "inquiries";
  const message = pending.phase === "error"
    ? "دریافت داده این تب ناموفق بود؛ داده تب قبلی عمداً نمایش داده نمی‌شود."
    : "در حال دریافت داده همین تب...";

  return <style>{`
    section[data-pdp-shared-notice-layout="${layout}"] > div:nth-last-of-type(2),
    section[data-pdp-shared-notice-layout="${layout}"] > div:last-of-type {
      display: none !important;
    }
    section[data-pdp-shared-notice-layout="${layout}"] .pdp-v2-row-count {
      visibility: hidden !important;
    }
    section[data-pdp-shared-notice-layout="${layout}"] .pdp-v9-filter-bar::after {
      content: "${message}";
      grid-column: 1 / -1;
      display: block;
      margin-top: 4px;
      padding: 10px 12px;
      border: 1px solid rgba(15, 23, 42, .12);
      border-radius: 10px;
      background: #f8fafc;
      font-weight: 700;
    }
  `}</style>;
}
