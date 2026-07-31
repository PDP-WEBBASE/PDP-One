"use client";

import { useState } from "react";
import AIReviewCenterPanel from "./AIReviewCenterPanel";
import ProcurementWorkspaceV15 from "./ProcurementWorkspaceV15";

export default function ProcurementWorkspaceV16() {
  const [reviewOpen, setReviewOpen] = useState(false);

  return <>
    <ProcurementWorkspaceV15 />
    <button
      type="button"
      onClick={() => setReviewOpen(true)}
      style={{
        position: "fixed",
        zIndex: 810,
        insetInlineStart: 20,
        bottom: 68,
        border: "1px solid rgba(15,118,110,.35)",
        borderRadius: 999,
        background: "#0f766e",
        color: "white",
        padding: "10px 14px",
        font: "inherit",
        fontWeight: 700,
        cursor: "pointer",
        boxShadow: "0 12px 28px rgba(15,23,42,.2)",
      }}
    >
      مرکز بازبینی AI
    </button>
    {reviewOpen && <AIReviewCenterPanel onClose={() => setReviewOpen(false)} />}
  </>;
}
