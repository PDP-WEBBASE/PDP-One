"use client";

import { useState } from "react";
import FastAnalysisContextManager, { AnalysisSection } from "./FastAnalysisContextManager";
import AnalysisEnginePanel from "./AnalysisEnginePanel";
import ProcurementWorkspaceV13 from "./ProcurementWorkspaceV13";

const floatingButtonStyle = {
  position: "fixed",
  zIndex: 800,
  border: "1px solid rgba(15,118,110,.35)",
  borderRadius: 999,
  color: "white",
  padding: "10px 14px",
  font: "inherit",
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 12px 28px rgba(15,23,42,.2)",
} as const;

/**
 * V14 is intentionally presentation-only.
 *
 * Request resilience belongs to scoped data/session clients. This component
 * MUST NOT patch window.fetch, impose a subsystem-wide timeout, retry failed
 * endpoints, or probe them in the background. Those behaviours previously
 * amplified transient slowness into a retry storm that could starve the small
 * synchronous Gunicorn worker pool.
 */
export default function ProcurementWorkspaceV14() {
  const [analysisSection, setAnalysisSection] = useState<AnalysisSection | null>(null);
  const [engineOpen, setEngineOpen] = useState(false);

  return <>
    <ProcurementWorkspaceV13 />
    <button
      type="button"
      data-pdp-analysis-context-manager="true"
      onClick={() => setAnalysisSection("prompts")}
      style={{
        ...floatingButtonStyle,
        insetInlineStart: 20,
        bottom: 20,
        background: "#0f766e",
      }}
    >
      تنظیمات تحلیل واقعی
    </button>
    <button
      type="button"
      onClick={() => setEngineOpen(true)}
      style={{
        ...floatingButtonStyle,
        insetInlineStart: 20,
        bottom: 70,
        background: "#1d4ed8",
        borderColor: "rgba(29,78,216,.35)",
      }}
    >
      موتور تحلیل PDP
    </button>
    {analysisSection && <FastAnalysisContextManager initialSection={analysisSection} onClose={() => setAnalysisSection(null)} />}
    {engineOpen && <AnalysisEnginePanel onClose={() => setEngineOpen(false)} />}
  </>;
}
