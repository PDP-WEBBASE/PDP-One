"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import AIReviewCenterPanel from "./AIReviewCenterPanel";
import AnalysisContextManager from "./AnalysisContextManager";
import AnalysisEnginePanel from "./AnalysisEnginePanel";
import AutomationControlPanel from "./AutomationControlPanel";
import CaseContractDraftPanel from "./CaseContractDraftPanel";
import CaseFollowUpPanel from "./CaseFollowUpPanel";
import InternetUsageMonitoringPanel from "./InternetUsageMonitoringPanel";
import ManagementDashboardPanel from "./ManagementDashboardPanel";
import OpportunityWorkflowPanel from "./OpportunityWorkflowPanel";
import ProcurementAnalysisCenterPanel from "./ProcurementAnalysisCenterPanel";
import { PROCUREMENT_STABLE_VIEW_STATE_EVENT } from "./procurementStableViewState";

type ToolKey = "workflow" | "review" | "followup" | "contract" | "dashboard" | "automation" | "analysis" | "analysisSettings" | "engine" | "internetUsage";

const TOOLS_TAB_ATTRIBUTE = "data-pdp-management-tools-tab";
const STABLE_READY_ATTRIBUTE = "data-pdp-management-tools-stable-ready";
const HOST_ID = "pdp-procurement-management-toolbar-stable";
const TOOLS_TAB_LABEL = "ابزارهای مدیریتی زیرسامانه";
const EXTRACTION_TAB_LABEL = "ابزارهای استخراج و تحلیل";
const LEGACY_FLOATING_LABELS = new Set([
  "مدیریت فرصت‌ها", "مرکز بازبینی AI", "قرارداد از پرونده برنده", "پیگیری مسئول و موعد",
  "داشبورد مدیریتی", "زمان‌بندی استخراج و AI", "مرکز تحلیل فراخوان‌ها", "تنظیمات تحلیل واقعی", "موتور تحلیل PDP", "پایش مصرف اینترنت",
]);
const tools: { key: ToolKey; label: string; description: string }[] = [
  { key: "workflow", label: "مدیریت فرصت‌ها", description: "مرحله، اقدام بعدی و تصمیم انسانی" },
  { key: "followup", label: "پیگیری مسئول و موعد", description: "مسئول، موعد و پیگیری پرونده‌ها" },
  { key: "review", label: "مرکز بازبینی AI", description: "بازبینی و کنترل پیش‌نویس‌های تحلیل" },
  { key: "analysis", label: "مرکز تحلیل فراخوان‌ها", description: "اجرای تحلیل و مشاهده وضعیت پردازش" },
  { key: "engine", label: "موتور تحلیل PDP", description: "اجرای موتور تحلیل PDP و مشاهده درخواست‌ها" },
  { key: "analysisSettings", label: "تنظیمات تحلیل واقعی", description: "Prompt، کلیدواژه، پروفایل و نسخه فعال تحلیل" },
  { key: "automation", label: "زمان‌بندی استخراج و AI", description: "کنترل اجرای دوره‌ای استخراج و تحلیل" },
  { key: "dashboard", label: "داشبورد مدیریتی", description: "نمای مدیریتی و شاخص‌های کلیدی" },
  { key: "internetUsage", label: "پایش مصرف اینترنت", description: "مصرف واقعی ثبت‌شده و پوشش اندازه‌گیری" },
  { key: "contract", label: "قرارداد از پرونده برنده", description: "ایجاد پیش‌نویس قرارداد از پرونده برنده" },
];

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function ActiveToolPanel({ tool, onClose }: { tool: ToolKey | null; onClose: () => void }) {
  if (tool === "workflow") return <OpportunityWorkflowPanel onClose={onClose} />;
  if (tool === "review") return <AIReviewCenterPanel onClose={onClose} />;
  if (tool === "followup") return <CaseFollowUpPanel onClose={onClose} />;
  if (tool === "contract") return <CaseContractDraftPanel onClose={onClose} />;
  if (tool === "dashboard") return <ManagementDashboardPanel onClose={onClose} />;
  if (tool === "internetUsage") return <InternetUsageMonitoringPanel onClose={onClose} />;
  if (tool === "automation") return <AutomationControlPanel onClose={onClose} />;
  if (tool === "analysis") return <ProcurementAnalysisCenterPanel onClose={onClose} />;
  if (tool === "analysisSettings") return <AnalysisContextManager initialSection="prompts" onClose={onClose} />;
  if (tool === "engine") return <AnalysisEnginePanel onClose={onClose} />;
  return null;
}

function ManagementToolbar({ onOpen }: { onOpen: (key: ToolKey) => void }) {
  return <section dir="rtl" style={{margin:"12px 0 16px",padding:14,border:"1px solid #dbe3ec",borderRadius:14,background:"#f8fafc"}}>
    <div style={{display:"flex",justifyContent:"space-between",gap:10,marginBottom:10,flexWrap:"wrap"}}><div><strong style={{display:"block",fontSize:17}}>ابزارهای مدیریتی زیرسامانه</strong><small style={{color:"#64748b"}}>ابزارهای مدیریتی و تحلیل بدون پایش دائمی DOM در این بخش قرار دارند.</small></div><span>۱۰ ابزار</span></div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(175px,1fr))",gap:8}}>{tools.map((tool) => <button key={tool.key} type="button" onClick={() => onOpen(tool.key)} style={{minHeight:62,textAlign:"right",border:"1px solid #dbe3ec",borderRadius:11,background:"white",padding:"10px 11px",font:"inherit",cursor:"pointer"}}><b style={{display:"block",fontSize:12.5,marginBottom:3}}>{tool.label}</b><small style={{color:"#64748b"}}>{tool.description}</small></button>)}</div>
  </section>;
}

export default function ProcurementManagementToolsStableEnhancement() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [toolsActive, setToolsActive] = useState(false);
  const [activeTool, setActiveTool] = useState<ToolKey | null>(null);

  const syncShell = useCallback(() => {
    const root = document.querySelector<HTMLElement>('main[dir="rtl"]');
    const nav = root?.querySelector("nav");
    if (!root || !nav) return;

    document.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
      const isLegacyFloatingAction = LEGACY_FLOATING_LABELS.has(normalize(button.textContent))
        && (button.style.position === "fixed" || window.getComputedStyle(button).position === "fixed");
      if (isLegacyFloatingAction) button.style.display = "none";
    });

    const nativeButtons = Array.from(nav.querySelectorAll<HTMLButtonElement>("button")).filter((button) => !button.hasAttribute(TOOLS_TAB_ATTRIBUTE));
    const managementButton = nativeButtons.find((button) => ["مدیریت زیرسامانه", EXTRACTION_TAB_LABEL].includes(normalize(button.textContent)));
    if (managementButton) managementButton.textContent = EXTRACTION_TAB_LABEL;
    let toolsButton = nav.querySelector<HTMLButtonElement>(`button[${TOOLS_TAB_ATTRIBUTE}]`);
    if (!toolsButton) {
      toolsButton = document.createElement("button");
      toolsButton.type = "button";
      toolsButton.setAttribute(TOOLS_TAB_ATTRIBUTE, "1");
      toolsButton.textContent = TOOLS_TAB_LABEL;
      nav.insertBefore(toolsButton, managementButton || null);
    }
    toolsButton.onclick = () => setToolsActive(true);
    let nextHost = document.getElementById(HOST_ID) as HTMLElement | null;
    if (!nextHost) {
      nextHost = document.createElement("div");
      nextHost.id = HOST_ID;
      nav.insertAdjacentElement("afterend", nextHost);
    }
    nextHost.style.display = toolsActive ? "block" : "none";
    Array.from(root.children).filter((child) => child.tagName === "SECTION").forEach((section) => {
      (section as HTMLElement).style.display = toolsActive ? "none" : "";
    });
    setHost((current) => current === nextHost ? current : nextHost);

    // InitialRenderBoundary must not reveal the underlying workspace until this
    // exact presentation cleanup has completed. This prevents the legacy fixed
    // action launchers and pre-stable nav shape from becoming a visible frame.
    root.setAttribute(STABLE_READY_ATTRIBUTE, "1");
  }, [toolsActive]);

  useEffect(() => {
    let frame1 = window.requestAnimationFrame(() => { window.requestAnimationFrame(syncShell); });
    const onState = () => {
      setToolsActive(false);
      window.cancelAnimationFrame(frame1);
      frame1 = window.requestAnimationFrame(() => { window.requestAnimationFrame(syncShell); });
    };
    const onClick = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest<HTMLButtonElement>("nav button") : null;
      if (button && !button.hasAttribute(TOOLS_TAB_ATTRIBUTE)) setToolsActive(false);
    };
    window.addEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener(PROCUREMENT_STABLE_VIEW_STATE_EVENT, onState);
      document.removeEventListener("click", onClick);
      window.cancelAnimationFrame(frame1);
      document.querySelector(`button[${TOOLS_TAB_ATTRIBUTE}]`)?.remove();
      document.getElementById(HOST_ID)?.remove();
      document.querySelector<HTMLElement>(`[${STABLE_READY_ATTRIBUTE}="1"]`)?.removeAttribute(STABLE_READY_ATTRIBUTE);
    };
  }, [syncShell]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(syncShell);
    return () => window.cancelAnimationFrame(frame);
  }, [syncShell]);

  return <>{host && toolsActive ? createPortal(<ManagementToolbar onOpen={setActiveTool}/>, host) : null}<ActiveToolPanel tool={activeTool} onClose={() => setActiveTool(null)}/></>;
}
