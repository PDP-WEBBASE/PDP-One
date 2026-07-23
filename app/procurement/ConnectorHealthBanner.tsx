"use client";

import { useEffect, useState } from "react";

type ConnectorHealth = {
  key: string;
  source: string;
  notice_type: "tender" | "inquiry";
  health: string;
  health_label: string;
  requires_attention: boolean;
  message: string;
  latest_run: null | {
    requested_page_cap: number | null;
    pages_processed: number;
    last_successful_page: number | null;
    reported_total_pages: number | null;
    records_seen: number;
    warnings: number;
    completeness: string;
    stop_reason: string;
    suspicious_pages: number[];
    recovered_pages: number[];
  };
};

type DashboardPayload = {
  sources?: {
    all_healthy?: boolean;
    attention_connectors?: number;
    connector_health?: ConnectorHealth[];
  };
};

const fa = new Intl.NumberFormat("fa-IR");

function typeLabel(value: ConnectorHealth["notice_type"]) {
  return value === "tender" ? "مناقصات" : "استعلامات";
}

export default function ConnectorHealthBanner({ embedded = false }: { embedded?: boolean }) {
  const [health, setHealth] = useState<ConnectorHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/procurement/dashboard/", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (!response.ok) throw new Error(`dashboard-${response.status}`);
        return response.json() as Promise<DashboardPayload>;
      })
      .then((payload) => {
        if (!active) return;
        setHealth(payload.sources?.connector_health || []);
        setUnavailable(false);
      })
      .catch(() => {
        if (!active) return;
        setUnavailable(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) return null;

  const attention = health.filter((item) => item.requires_attention);
  const healthy = health.filter((item) => !item.requires_attention && item.health === "healthy");

  return (
    <section
      dir="rtl"
      aria-label="سلامت منابع استخراج"
      style={{
        margin: embedded ? 0 : "16px auto 0",
        maxWidth: embedded ? "none" : 1440,
        padding: embedded ? 0 : "0 24px",
        fontFamily: "inherit",
      }}
    >
      <div
        style={{
          border: "1px solid rgba(15, 23, 42, 0.16)",
          borderRadius: 16,
          background: "#ffffff",
          padding: embedded ? 14 : 16,
          boxShadow: embedded ? "none" : "0 8px 24px rgba(15, 23, 42, 0.06)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <strong style={{ display: "block", fontSize: 16 }}>سلامت آخرین استخراج هر منبع</strong>
            <span style={{ fontSize: 13, color: "#475569" }}>
              این اطلاعات فقط در زیرتب «گزارش استخراج» نمایش داده می‌شوند.
            </span>
          </div>
          <strong style={{ color: attention.length ? "#b45309" : "#047857" }}>
            {unavailable
              ? "وضعیت منابع در دسترس نیست"
              : attention.length
                ? `${fa.format(attention.length)} مورد نیازمند توجه`
                : `${fa.format(healthy.length)} Connector سالم`}
          </strong>
        </div>

        {!unavailable && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
              gap: 8,
              marginTop: 12,
            }}
          >
            {health.map((item) => {
              const run = item.latest_run;
              const attentionItem = item.requires_attention;
              return (
                <article
                  key={item.key}
                  style={{
                    border: `1px solid ${attentionItem ? "rgba(180, 83, 9, 0.35)" : "rgba(4, 120, 87, 0.28)"}`,
                    borderRadius: 12,
                    padding: 10,
                    background: attentionItem ? "#fffbeb" : "#ecfdf5",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <strong>{item.source} ـ {typeLabel(item.notice_type)}</strong>
                    <span style={{ fontWeight: 700 }}>{item.health_label}</span>
                  </div>
                  <p style={{ margin: "7px 0", fontSize: 12 }}>{item.message}</p>
                  {run && (
                    <small style={{ display: "block", color: "#475569", lineHeight: 1.8 }}>
                      صفحات: {fa.format(run.pages_processed)}
                      {run.requested_page_cap ? ` از سقف ${fa.format(run.requested_page_cap)}` : ""}
                      {run.reported_total_pages !== null ? ` · کل اعلامی ${fa.format(run.reported_total_pages)}` : ""}
                      {run.last_successful_page !== null ? ` · آخرین سالم ${fa.format(run.last_successful_page)}` : ""}
                      {run.suspicious_pages.length ? ` · مشکوک ${run.suspicious_pages.map((page) => fa.format(page)).join("، ")}` : ""}
                      {` · رکورد ${fa.format(run.records_seen)}`}
                    </small>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
