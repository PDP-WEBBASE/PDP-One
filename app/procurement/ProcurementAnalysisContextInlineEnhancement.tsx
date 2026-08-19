"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import FastAnalysisContextManager, { AnalysisSection } from "./FastAnalysisContextManager";

const sectionByLabel: Record<string, AnalysisSection> = {
  "نقش و Prompt": "prompts",
  "کلیدواژه‌ها": "keywords",
  "پروفایل، صلاحیت و رزومه": "company",
  "نسخه‌ها و فعال‌سازی": "versions",
};

function isAnalysisManagementTabs(element: HTMLElement | null) {
  if (!element) return false;
  const labels = Array.from(element.querySelectorAll(":scope > button")).map((button) => (button.textContent || "").trim());
  return ["نقش و Prompt", "کلیدواژه‌ها", "پروفایل، صلاحیت و رزومه", "نسخه‌ها و فعال‌سازی"].every((label) => labels.includes(label));
}

export default function ProcurementAnalysisContextInlineEnhancement() {
  const [section, setSection] = useState<AnalysisSection | null>(null);
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const button = (event.target as HTMLElement | null)?.closest("button") as HTMLButtonElement | null;
      if (!button) return;
      const tabs = button.parentElement;
      if (!isAnalysisManagementTabs(tabs)) return;
      const label = (button.textContent || "").trim();
      const nextSection = sectionByLabel[label];
      if (!nextSection) {
        setSection(null);
        setPortalTarget(null);
        return;
      }
      setSection(nextSection);
      window.setTimeout(() => {
        const content = tabs?.nextElementSibling as HTMLElement | null;
        if (content?.isConnected) setPortalTarget(content);
      }, 0);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    if (!portalTarget) return;
    const previous = new Map<HTMLElement, string>();
    const hideLegacyChildren = () => {
      Array.from(portalTarget.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) return;
        if (child.dataset.pdpAnalysisContextInline === "true") return;
        if (!previous.has(child)) previous.set(child, child.style.display);
        child.style.display = "none";
      });
    };
    hideLegacyChildren();
    const observer = new MutationObserver(hideLegacyChildren);
    observer.observe(portalTarget, { childList: true });
    return () => {
      observer.disconnect();
      previous.forEach((display, child) => {
        if (child.isConnected) child.style.display = display;
      });
    };
  }, [portalTarget]);

  if (!section || !portalTarget || !portalTarget.isConnected) return null;
  return createPortal(
    <div data-pdp-analysis-context-inline="true" style={{ gridColumn: "1 / -1", width: "100%" }}>
      <FastAnalysisContextManager key={section} inline initialSection={section} />
    </div>,
    portalTarget,
  );
}
