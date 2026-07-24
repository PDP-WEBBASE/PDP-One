"use client";

import { useEffect, useState } from "react";
import AnalysisContextManager from "./AnalysisContextManager";
import ProcurementWorkspaceV13 from "./ProcurementWorkspaceV13";

type AnalysisSection = "prompts" | "keywords" | "company" | "versions";

const labelToSection: Record<string, AnalysisSection> = {
  "نقش و Prompt": "prompts",
  "کلیدواژه‌ها": "keywords",
  "پروفایل، صلاحیت و رزومه": "company",
  "نسخه‌ها و فعال‌سازی": "versions",
};

export default function ProcurementWorkspaceV14() {
  const [analysisSection, setAnalysisSection] = useState<AnalysisSection | null>(null);

  useEffect(() => {
    if (analysisSection) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const button = target?.closest("button");
      if (!button) return;
      const section = labelToSection[(button.textContent || "").trim()];
      if (!section) return;
      setAnalysisSection(section);
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [analysisSection]);

  return <>
    <ProcurementWorkspaceV13 />
    <button
      type="button"
      onClick={() => setAnalysisSection("prompts")}
      style={{
        position: "fixed",
        insetInlineStart: 20,
        bottom: 20,
        zIndex: 800,
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
      تنظیمات تحلیل واقعی
    </button>
    {analysisSection && <AnalysisContextManager initialSection={analysisSection} onClose={() => setAnalysisSection(null)} />}
  </>;
}
