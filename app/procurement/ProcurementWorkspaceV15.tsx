"use client";

import { useState } from "react";
import OpportunityWorkflowPanel from "./OpportunityWorkflowPanel";
import ProcurementWorkspaceV14 from "./ProcurementWorkspaceV14";

export default function ProcurementWorkspaceV15() {
  const [workflowOpen, setWorkflowOpen] = useState(false);

  return <>
    <ProcurementWorkspaceV14 />
    <button
      type="button"
      onClick={() => setWorkflowOpen(true)}
      style={{
        position: "fixed",
        zIndex: 800,
        insetInlineStart: 20,
        bottom: 120,
        border: "1px solid rgba(109,40,217,.35)",
        borderRadius: 999,
        background: "#6d28d9",
        color: "white",
        padding: "10px 14px",
        font: "inherit",
        fontWeight: 700,
        cursor: "pointer",
        boxShadow: "0 12px 28px rgba(15,23,42,.2)",
      }}
    >
      مدیریت فرصت‌ها
    </button>
    {workflowOpen && <OpportunityWorkflowPanel onClose={() => setWorkflowOpen(false)} />}
  </>;
}
