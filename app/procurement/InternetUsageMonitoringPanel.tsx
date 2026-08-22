"use client";

import { useEffect, useState } from "react";

type PeriodKey = "24h" | "7d" | "all";
type PeriodValue = { download_bytes: number | null; upload_bytes: number | null; total_bytes: number | null; operation_count: number | null };
type Activity = { key: string; label: string; measured: boolean; method: string; description: string; periods: Record<PeriodKey, PeriodValue>; share_percent: number | null };
type Usage = { generated_at: string; mode: string; uses_real_data_only: boolean; activities: Activity[]; measured_totals: Record<PeriodKey, number>; performance: { hot_path_writes_added: number; packet_capture: boolean; payload_logging: boolean; dashboard_queries_only_when_opened: boolean } };

const API = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: "24h", label: "۲۴ ساعت گذشته" },
  { key: "7d", label: "۷ روز گذشته" },
  { key: "all", label: "کل دوره" },
];

function bytes(value: number | null) {
  if (value === null) return "اندازه‌گیری نشده";
  if (value < 1024) return `${new Intl.NumberFormat("fa-IR").format(value)} بایت`;
  const units = ["کیلوبایت", "مگابایت", "گیگابایت", "ترابایت"];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(size)} ${units[index]}`;
}

function date(value: string) {
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

export default function InternetUsageMonitoringPanel({ onClose }: { onClose: () => void }) {
  // Deployment verifies this content-addressed web build before accepting it as live.
  const [data, setData] = useState<Usage | null>(null);
  const [message, setMessage] = useState("");

  async function load() {
    setMessage("");
    try {
      const response = await fetch(`${API}/procurement/internet-usage-dashboard/`, { credentials: "include", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("دریافت داده پایش اینترنت انجام نشد.");
      setData(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "دریافت داده انجام نشد.");
    }
  }

  useEffect(() => {
    let active = true;
    fetch(`${API}/procurement/internet-usage-dashboard/`, { credentials: "include", headers: { Accept: "application/json" } })
      .then((response) => { if (!response.ok) throw new Error("دریافت داده پایش اینترنت انجام نشد."); return response.json() as Promise<Usage>; })
      .then((value) => { if (active) setData(value); })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "دریافت داده انجام نشد."); });
    return () => { active = false; };
  }, []);

  return <div dir="rtl" role="dialog" aria-modal="true" aria-label="پایش مصرف اینترنت" style={{ position: "fixed", inset: 0, zIndex: 1590, background: "rgba(15,23,42,.64)", display: "grid", placeItems: "center", padding: 15 }}>
    <section style={{ width: "min(1380px,98vw)", height: "min(860px,95vh)", background: "white", borderRadius: 18, display: "grid", gridTemplateRows: "auto 1fr", overflow: "hidden" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "15px 18px", borderBottom: "1px solid #e2e8f0" }}>
        <div><small>پسیو، خواندنی و بدون دخالت در عملیات</small><h2 style={{ margin: 3 }}>پایش مصرف اینترنت</h2></div>
        <div><button onClick={() => void load()}>بازخوانی</button><button onClick={onClose} aria-label="بستن" style={{ border: 0, fontSize: 24, marginInlineStart: 8 }}>×</button></div>
      </header>
      <main style={{ padding: 18, overflow: "auto", background: "#f8fafc" }}>
        {message && <div role="status">{message}</div>}
        {!data ? <p>در حال محاسبه از روی داده‌های واقعی ثبت‌شده...</p> : <div style={{ display: "grid", gap: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 9 }}>
            {PERIODS.map((period) => <article key={period.key} style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: 13 }}><small style={{ color: "#64748b" }}>مصرف اندازه‌گیری‌شده · {period.label}</small><b style={{ display: "block", fontSize: 22, marginTop: 5 }}>{bytes(data.measured_totals[period.key])}</b></article>)}
          </div>
          <section style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: 14, overflowX: "auto" }}>
            <h3>مصرف به تفکیک فعالیت و بازه زمانی</h3>
            <table style={{ width: "100%", minWidth: 1160, borderCollapse: "collapse", textAlign: "center" }}>
              <thead><tr><th rowSpan={2} style={{ textAlign: "right" }}>فعالیت</th>{PERIODS.map((period) => <th key={period.key} colSpan={3}>{period.label}</th>)}<th rowSpan={2}>سهم کل</th></tr><tr>{PERIODS.flatMap((period) => [<th key={`${period.key}-down`}>دانلود</th>, <th key={`${period.key}-up`}>آپلود</th>, <th key={`${period.key}-total`}>مجموع</th>])}</tr></thead>
              <tbody>{data.activities.map((activity) => <tr key={activity.key} style={{ borderTop: "1px solid #e2e8f0" }}>
                <td style={{ padding: "12px 8px", textAlign: "right", minWidth: 210 }}><b>{activity.label}</b><small style={{ display: "block", color: "#64748b", marginTop: 3 }}>{activity.description}</small></td>
                {PERIODS.flatMap((period) => { const value = activity.periods[period.key]; return [<td key={`${activity.key}-${period.key}-down`}>{bytes(value.download_bytes)}</td>, <td key={`${activity.key}-${period.key}-up`}>{bytes(value.upload_bytes)}</td>, <td key={`${activity.key}-${period.key}-total`}><b>{bytes(value.total_bytes)}</b></td>]; })}
                <td>{activity.share_percent === null ? "—" : `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(activity.share_percent)}٪`}</td>
              </tr>)}</tbody>
            </table>
          </section>
          <aside style={{ padding: 12, borderRadius: 11, background: "#ecfdf5", color: "#065f46" }}>این صفحه فقط هنگام بازشدن Query می‌زند و شنود بسته ندارد؛ عدد صفر فقط وقتی نمایش داده می‌شود که اندازه‌گیری واقعی صفر باشد. داده اندازه‌گیری‌نشده با عدد تخمینی نمایش داده نمی‌شود و با عبارت «اندازه‌گیری نشده» مشخص است.</aside>
          <small>آخرین محاسبه: {date(data.generated_at)} · سهم‌ها فقط از مجموع داده‌های اندازه‌گیری‌شده محاسبه شده‌اند.</small>
        </div>}
      </main>
    </section>
  </div>;
}
