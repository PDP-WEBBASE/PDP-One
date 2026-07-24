"use client";

import { useEffect, useMemo, useState } from "react";

type OperationalNote = {
  reason?: string;
  reviewed_at?: string;
  can_enable_manually?: boolean;
};

type Connector = {
  id: string;
  key: string;
  notice_type: "tender" | "inquiry";
  notice_type_label: string;
  enabled: boolean;
  status: string;
  status_label: string;
  operational_note: OperationalNote | null;
};

type Source = {
  id: string;
  key: string;
  name: string;
  enabled: boolean;
  status: string;
  status_label: string;
  connectors: Connector[];
};

type SourceListPayload = Source[] | { results?: Source[] };
type Mode = "loading" | "live" | "preview" | "unauthorized" | "error";

const previewSources: Source[] = [
  {
    id: "preview-hezareh",
    key: "hezareh",
    name: "هزاره",
    enabled: true,
    status: "active",
    status_label: "فعال",
    connectors: [
      { id: "preview-hezareh-tender", key: "hezareh_tenders", notice_type: "tender", notice_type_label: "مناقصات", enabled: true, status: "active", status_label: "فعال", operational_note: null },
      { id: "preview-hezareh-inquiry", key: "hezareh_inquiries", notice_type: "inquiry", notice_type_label: "استعلامات", enabled: true, status: "active", status_label: "فعال", operational_note: null },
    ],
  },
  {
    id: "preview-parsnamad",
    key: "parsnamad",
    name: "پارس‌نماد داده",
    enabled: true,
    status: "active",
    status_label: "فعال",
    connectors: [
      {
        id: "preview-parsnamad-tender",
        key: "parsnamad_tenders",
        notice_type: "tender",
        notice_type_label: "مناقصات",
        enabled: false,
        status: "inactive",
        status_label: "غیرفعال",
        operational_note: {
          reason: "مسیر عمومی مناقصات این سایت در حال حاضر همان محتوای استعلامات را برمی‌گرداند؛ برای جلوگیری از ثبت داده نادرست غیرفعال شده است.",
          reviewed_at: "2026-07-23",
          can_enable_manually: true,
        },
      },
      { id: "preview-parsnamad-inquiry", key: "parsnamad_inquiries", notice_type: "inquiry", notice_type_label: "استعلامات", enabled: true, status: "active", status_label: "فعال", operational_note: null },
    ],
  },
  {
    id: "preview-setad",
    key: "setad",
    name: "ستاد ایران",
    enabled: true,
    status: "active",
    status_label: "فعال",
    connectors: [
      { id: "preview-setad-tender", key: "setad_tenders", notice_type: "tender", notice_type_label: "مناقصات", enabled: true, status: "active", status_label: "فعال", operational_note: null },
      { id: "preview-setad-inquiry", key: "setad_inquiries", notice_type: "inquiry", notice_type_label: "استعلامات", enabled: true, status: "active", status_label: "فعال", operational_note: null },
    ],
  },
];

function csrfToken() {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function connectorLabel(connector: Connector) {
  return connector.notice_type === "tender" ? "مناقصات" : "استعلامات";
}

export default function ExtractionSourceControls() {
  const [sources, setSources] = useState<Source[]>(previewSources);
  const [mode, setMode] = useState<Mode>("loading");
  const [updating, setUpdating] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/v1/procurement/sources/", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        if (response.status === 401 || response.status === 403) {
          if (active) setMode("unauthorized");
          return null;
        }
        if (!response.ok) throw new Error(`sources-${response.status}`);
        return response.json() as Promise<SourceListPayload>;
      })
      .then((payload) => {
        if (!active || payload === null) return;
        const nextSources = Array.isArray(payload) ? payload : payload.results || [];
        setSources(nextSources);
        setMode("live");
      })
      .catch(() => {
        if (!active) return;
        setMode(typeof window !== "undefined" ? "preview" : "error");
      });
    return () => {
      active = false;
    };
  }, []);

  const enabledCount = useMemo(
    () => sources.reduce((total, source) => total + source.connectors.filter((item) => item.enabled).length, 0),
    [sources],
  );

  function replaceConnector(updated: Connector) {
    setSources((current) => current.map((source) => ({
      ...source,
      enabled: source.id === String(updated.id) ? updated.enabled : source.enabled,
      connectors: source.connectors.map((connector) => connector.id === updated.id ? updated : connector),
    })));
  }

  async function toggleConnector(sourceId: string, connector: Connector) {
    const nextEnabled = !connector.enabled;
    setMessage("");

    if (mode === "unauthorized") {
      setMessage("برای تغییر منابع استخراج باید با حساب مدیر سیستم وارد شوید.");
      return;
    }

    if (mode !== "live") {
      setSources((current) => current.map((source) => source.id !== sourceId ? source : ({
        ...source,
        connectors: source.connectors.map((item) => item.id === connector.id ? {
          ...item,
          enabled: nextEnabled,
          status: nextEnabled ? "active" : "inactive",
          status_label: nextEnabled ? "فعال" : "غیرفعال",
        } : item),
      })));
      setMode("preview");
      setMessage("حالت Preview: وضعیت نمایشی تغییر کرد و در پایگاه‌داده ذخیره نشد.");
      return;
    }

    setUpdating(connector.id);
    try {
      const token = csrfToken();
      const response = await fetch(`/api/v1/procurement/connectors/${connector.id}/`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...(token ? { "X-CSRFToken": token } : {}),
        },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      if (response.status === 401 || response.status === 403) {
        setMode("unauthorized");
        throw new Error("unauthorized");
      }
      if (!response.ok) throw new Error(`connector-${response.status}`);
      const updated = await response.json() as Connector;
      replaceConnector(updated);
      setMessage(`${connectorLabel(updated)} ${sources.find((source) => source.id === sourceId)?.name || "سایت"} ${updated.enabled ? "فعال" : "غیرفعال"} شد.`);
    } catch (error) {
      setMessage(error instanceof Error && error.message === "unauthorized"
        ? "فقط مدیر سیستم اجازه تغییر منابع استخراج را دارد."
        : "ذخیره تنظیم Connector انجام نشد؛ وضعیت قبلی حفظ شده است.");
    } finally {
      setUpdating(null);
    }
  }

  return (
    <article
      dir="rtl"
      aria-label="منابع استخراج"
      style={{
        border: "1px solid rgba(15, 23, 42, 0.14)",
        borderRadius: 16,
        background: "#fff",
        padding: 18,
        boxShadow: "0 8px 24px rgba(15, 23, 42, 0.05)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>منابع استخراج</h2>
          <p style={{ margin: "7px 0 0", color: "#475569", fontSize: 13 }}>
            مناقصات و استعلامات هر سایت مستقل هستند؛ خاموش‌کردن یکی، دیگری را متوقف نمی‌کند.
          </p>
        </div>
        <strong style={{ color: "#0f766e" }}>{enabledCount.toLocaleString("fa-IR")} Connector فعال</strong>
      </div>

      {mode === "preview" && <p role="status" style={{ padding: 10, borderRadius: 10, background: "#eff6ff", color: "#1d4ed8", fontSize: 13 }}>حالت Preview فعال است؛ تغییر تیک‌ها فقط نمایشی است.</p>}
      {mode === "unauthorized" && <p role="status" style={{ padding: 10, borderRadius: 10, background: "#fff7ed", color: "#9a3412", fontSize: 13 }}>برای مشاهده وضعیت واقعی یا تغییر آن، ورود با حساب مجاز لازم است.</p>}
      {message && <p role="status" style={{ padding: 10, borderRadius: 10, background: "#f8fafc", color: "#334155", fontSize: 13 }}>{message}</p>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 14 }}>
        {sources.map((source) => (
          <section key={source.id} style={{ border: "1px solid rgba(15, 23, 42, 0.12)", borderRadius: 14, padding: 14, background: "#f8fafc" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
              <strong>{source.name}</strong>
              <small style={{ color: source.enabled ? "#047857" : "#b91c1c", fontWeight: 700 }}>{source.status_label}</small>
            </div>

            <div style={{ display: "grid", gap: 10, marginTop: 13 }}>
              {["tender", "inquiry"].map((noticeType) => {
                const connector = source.connectors.find((item) => item.notice_type === noticeType);
                if (!connector) return null;
                const busy = updating === connector.id;
                return (
                  <label key={connector.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10, alignItems: "start", padding: 11, borderRadius: 11, background: connector.enabled ? "#ecfdf5" : "#fff7ed", cursor: busy ? "wait" : "pointer" }}>
                    <input
                      type="checkbox"
                      checked={connector.enabled}
                      disabled={busy || mode === "loading"}
                      onChange={() => toggleConnector(source.id, connector)}
                      aria-label={`${connectorLabel(connector)} ${source.name}`}
                      style={{ width: 18, height: 18, marginTop: 1 }}
                    />
                    <span>
                      <b style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span>{connectorLabel(connector)}</span>
                        <small style={{ color: connector.enabled ? "#047857" : "#b45309" }}>{busy ? "در حال ذخیره" : connector.status_label}</small>
                      </b>
                      {connector.operational_note?.reason && (
                        <small style={{ display: "block", marginTop: 6, lineHeight: 1.7, color: "#7c2d12" }}>
                          {connector.operational_note.reason}
                        </small>
                      )}
                    </span>
                  </label>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </article>
  );
}
