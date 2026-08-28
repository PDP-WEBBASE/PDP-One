"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { emitProcurementUiSync } from "./procurementUiSync";

const metricLabels = [
  "کل فراخوان‌ها",
  "فراخوان جدید امروز",
  "تحلیل‌نشده",
  "پیشنهادی",
  "منتخب",
  "ارسال‌شده",
  "مهلت تا ۷ روز",
  "نتیجه موفق",
];

function ApprovedLoadingShell() {
  return <div dir="rtl" aria-label="در حال آماده‌سازی نمای تاییدشده" style={{ minHeight: "100vh", background: "#f4f7f9", padding: "28px 32px", boxSizing: "border-box" }}>
    <header style={{ minHeight: 190, borderRadius: 28, background: "linear-gradient(105deg,#0d4653,#17656d)", color: "white", padding: "28px 34px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24 }}>
      <button type="button" disabled style={{ border: 0, borderRadius: 12, background: "rgba(255,255,255,.12)", color: "white", padding: "12px 16px", font: "inherit", fontWeight: 700 }}>بازگشت به سامانه</button>
      <div style={{ textAlign: "right" }}><small style={{ opacity: .85 }}>زیرسامانه تخصصی PDP One</small><h1 style={{ margin: "20px 0 10px", fontSize: 36, lineHeight: 1.2 }}>مناقصات و استعلامات</h1></div>
    </header>

    <nav style={{ marginTop: 26, minHeight: 62, border: "1px solid #e2e8f0", borderRadius: 16, background: "white", padding: "7px 10px", display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
      {["داشبورد مدیریتی", "مناقصات", "استعلامات", "ارجاعات مستقیم", "ابزارهای مدیریتی زیرسامانه", "ابزارهای استخراج و تحلیل"].map((label, index) => <span key={label} style={{ borderRadius: 11, padding: "10px 14px", background: index === 0 ? "#126271" : "transparent", color: index === 0 ? "white" : "#334155", fontWeight: index === 0 ? 700 : 500 }}>{label}</span>)}
    </nav>

    <section style={{ marginTop: 24, border: "1px solid #dbe3ec", borderRadius: 16, background: "white", padding: 14, boxShadow: "0 4px 14px rgba(15,23,42,.04)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 12 }}><div><h2 style={{ margin: "0 0 4px", fontSize: 18 }}>شاخص‌های مدیریتی</h2><small style={{ color: "#64748b" }}>محاسبه مستقیم سمت سرور؛ تفکیک مناقصه و استعلام</small></div><small style={{ color: "#94a3b8" }}>در حال دریافت داده…</small></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
        {metricLabels.map((label) => <div key={label} style={{ minHeight: 78, border: "1px solid #e2e8f0", borderRadius: 11, background: "#f8fafc", padding: "9px 10px" }}><span style={{ display: "block", color: "#64748b", fontSize: 12 }}>{label}</span><b style={{ display: "block", marginTop: 8, fontSize: 20, color: "#cbd5e1" }}>—</b><small style={{ color: "#cbd5e1" }}>مناقصه — · استعلام —</small></div>)}
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10, paddingTop: 10, borderTop: "1px solid #e2e8f0", color: "#94a3b8", fontSize: 11 }}><span>پیگیری عقب‌افتاده: —</span><span>بدون مسئول: —</span><span>ارجاع مستقیم فعال: —</span></div>
    </section>
  </div>;
}

export default function ProcurementInitialRenderBoundary({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const checkReady = () => {
      const compactDashboardHost = root.querySelector("#pdp-procurement-compact-dashboard-host");
      const managementToolsStable = root.querySelector('[data-pdp-management-tools-stable-ready="1"]');
      if (!compactDashboardHost || !managementToolsStable) {
        emitProcurementUiSync({ source: "initial-render-boundary", dashboard: true, management: true });
        return false;
      }
      setReady(true);
      return true;
    };

    if (checkReady()) return;
    const observer = new MutationObserver(() => {
      if (checkReady()) observer.disconnect();
    });
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-pdp-management-tools-stable-ready"] });
    return () => observer.disconnect();
  }, []);

  return <div ref={rootRef} data-pdp-initial-render-ready={ready ? "1" : "0"} style={{ position: "relative", minHeight: "100vh" }}>
    <div aria-hidden={ready} style={{ display: ready ? "none" : "block", position: "absolute", inset: 0, zIndex: 950, background: "#f4f7f9" }}><ApprovedLoadingShell /></div>
    <div aria-hidden={!ready} style={{ visibility: ready ? "visible" : "hidden" }}>{children}</div>
  </div>;
}
