"use client";

import { useEffect } from "react";

const APPLICABLE_TABS = new Set(["مناقصات", "استعلامات", "ارجاعات مستقیم"]);
const LONG_TITLE_THRESHOLD = 220;

function normalize(value: string | null | undefined) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function activeTopTab() {
  const nav = document.querySelector("main[dir='rtl'] nav");
  return normalize(Array.from(nav?.querySelectorAll<HTMLButtonElement>("button") || []).find((button) =>
    APPLICABLE_TABS.has(normalize(button.textContent)) && Boolean(normalize(button.className)),
  )?.textContent);
}

function applyTitlePresentation() {
  if (!APPLICABLE_TABS.has(activeTopTab())) return;
  const main = document.querySelector<HTMLElement>("main[dir='rtl']");
  if (!main) return;

  main.querySelectorAll<HTMLElement>("article.pdp-compact-record h3").forEach((heading) => {
    heading.classList.add("pdp-full-title");
    heading.classList.toggle("pdp-full-title-long", normalize(heading.textContent).length > LONG_TITLE_THRESHOLD);
  });
}

export default function ProcurementFullTitleEnhancement() {
  useEffect(() => {
    let scheduled = false;
    const apply = () => {
      scheduled = false;
      applyTitlePresentation();
    };
    const observer = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(apply);
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    apply();
    return () => observer.disconnect();
  }, []);

  return <style>{`
    .pdp-compact-record h3.pdp-full-title {
      display:block!important;
      max-width:100%!important;
      white-space:normal!important;
      overflow:visible!important;
      text-overflow:clip!important;
      -webkit-line-clamp:unset!important;
    }
    .pdp-compact-record h3.pdp-full-title.pdp-full-title-long {
      display:-webkit-box!important;
      overflow:hidden!important;
      white-space:normal!important;
      text-overflow:clip!important;
      -webkit-box-orient:vertical;
      -webkit-line-clamp:2!important;
    }
  `}</style>;
}
