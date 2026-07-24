"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./analysis-engine-panel.module.css";

type AnalysisRequest = {
  id: string;
  trigger: string;
  trigger_label: string;
  status: string;
  status_label: string;
  context_version: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  metadata: Record<string, unknown>;
};

type AnalysisDraft = {
  id: string;
  notice: string;
  notice_title: string;
  is_recommended: boolean;
  score: number;
  priority: string;
  priority_label: string;
  fit_for_pdp: string;
  reason: string;
  recommended_action: string;
  risk_notes: unknown[];
  confidence: string;
  review_status: string;
  review_status_label: string;
  analyzed_at: string;
};

type Collection<T> = T[] | { results?: T[] };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const ENGINE_API = `${API_BASE}/procurement/analysis/engine`;
const PROCUREMENT_API = `${API_BASE}/procurement`;
const fa = new Intl.NumberFormat("fa-IR");
const dateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function collection<T>(payload: Collection<T>): T[] {
  return Array.isArray(payload) ? payload : payload.results || [];
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTime.format(parsed);
}

async function csrfToken(): Promise<string> {
  const response = await fetch(`${API_BASE}/auth/session/`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("دریافت نشست امنیتی انجام نشد.");
  const payload = (await response.json()) as { csrf_token?: string };
  return String(payload.csrf_token || "");
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") return payload.detail;
    return Object.values(payload).flat().join(" ") || `خطای HTTP ${response.status}`;
  } catch {
    return `خطای HTTP ${response.status}`;
  }
}

export default function AnalysisEnginePanel({ onClose }: { onClose: () => void }) {
  const [requests, setRequests] = useState<AnalysisRequest[]>([]);
  const [drafts, setDrafts] = useState<AnalysisDraft[]>([]);
  const [contextVersion, setContextVersion] = useState<number | null>(null);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const latest = requests[0] || null;
  const aiDrafts = useMemo(() => drafts.filter((item) => item.review_status === "ai_draft"), [drafts]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [requestResponse, draftResponse, contextResponse] = await Promise.all([
        fetch(`${PROCUREMENT_API}/analysis-requests/?ordering=-created_at`, {
          credentials: "include",
          headers: { Accept: "application/json" },
          cache: "no-store",
        }),
        fetch(`${PROCUREMENT_API}/analysis-drafts/?ordering=-analyzed_at`, {
          credentials: "include",
          headers: { Accept: "application/json" },
          cache: "no-store",
        }),
        fetch(`${PROCUREMENT_API}/analysis/context/manifest/`, {
          credentials: "include",
          headers: { Accept: "application/json" },
          cache: "no-store",
        }),
      ]);
      if (!requestResponse.ok) throw new Error(await responseError(requestResponse));
      if (!draftResponse.ok) throw new Error(await responseError(draftResponse));
      if (!contextResponse.ok) throw new Error(await responseError(contextResponse));
      const requestItems = collection<AnalysisRequest>(await requestResponse.json()).sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      const draftItems = collection<AnalysisDraft>(await draftResponse.json()).sort(
        (a, b) => new Date(b.analyzed_at).getTime() - new Date(a.analyzed_at).getTime(),
      );
      const context = (await contextResponse.json()) as { context_version?: number };
      setRequests(requestItems);
      setDrafts(draftItems);
      setContextVersion(typeof context.context_version === "number" ? context.context_version : null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "دریافت وضعیت موتور تحلیل انجام نشد.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 6000);
  }

  async function startAnalysis() {
    setBusy("start");
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${ENGINE_API}/start/`, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": token,
        },
        body: JSON.stringify({ trigger: "manual_web", limit }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as { request?: AnalysisRequest; work_count?: number };
      await load();
      const count = payload.work_count || 0;
      notify(
        count
          ? `درخواست PDP برای ${fa.format(count)} فراخوان ساخته شد. اکنون در ChatGPT فرمان «PDP» را اجرا کنید.`
          : "فراخوان تحلیل‌نشده‌ای برای نسخه فعال پیدا نشد.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "شروع تحلیل انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  async function reviewDraft(draft: AnalysisDraft, reviewStatus: "reviewed" | "published" | "rejected") {
    const labels = { reviewed: "بازبینی‌شده", published: "منتشرشده", rejected: "ردشده" };
    if (!window.confirm(`نتیجه «${draft.notice_title}» به وضعیت ${labels[reviewStatus]} تغییر کند؟`)) return;
    setBusy(`${reviewStatus}-${draft.id}`);
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${ENGINE_API}/drafts/${draft.id}/review/`, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": token,
        },
        body: JSON.stringify({ review_status: reviewStatus }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      await load();
      notify(`نتیجه به وضعیت ${labels[reviewStatus]} تغییر کرد.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "بازبینی نتیجه انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" aria-label="موتور تحلیل PDP">
      <section className={styles.panel} dir="rtl">
        <header className={styles.header}>
          <div>
            <span>موتور تحلیل هوشمند</span>
            <h2>تحلیل فراخوان‌ها با فرمان PDP</h2>
            <p>هر نتیجه ابتدا پیش‌نویس ChatGPT است و فقط با تصمیم مدیر منتشر یا رد می‌شود.</p>
          </div>
          <button type="button" onClick={onClose} className={styles.closeButton}>بستن</button>
        </header>

        {message && <div className={styles.success}>{message}</div>}
        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.summaryGrid}>
          <article><span>نسخه فعال تنظیمات</span><b>{contextVersion === null ? "—" : fa.format(contextVersion)}</b></article>
          <article><span>آخرین وضعیت</span><b>{latest?.status_label || "بدون اجرا"}</b></article>
          <article><span>پیش‌نویس نیازمند بازبینی</span><b>{fa.format(aiDrafts.length)}</b></article>
        </div>

        <section className={styles.startCard}>
          <div>
            <h3>شروع اجرای دستی</h3>
            <p>سامانه فراخوان‌های جدید یا تغییرکرده و تحلیل‌نشده را با Snapshot فعال قفل می‌کند.</p>
          </div>
          <label>
            تعداد هر اجرا
            <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
              {[5, 10, 20, 30, 50].map((value) => <option key={value} value={value}>{fa.format(value)}</option>)}
            </select>
          </label>
          <button type="button" onClick={startAnalysis} disabled={busy === "start" || loading} className={styles.primaryButton}>
            {busy === "start" ? "در حال ساخت Request..." : "شروع درخواست PDP"}
          </button>
        </section>

        <div className={styles.notice}>
          پس از ساخته‌شدن Request، در همین گفت‌وگو فرمان <b>PDP</b> را بدهید. ChatGPT بسته کار را از سامانه می‌خواند، Draftها را ذخیره می‌کند و Request را می‌بندد.
        </div>

        <section className={styles.section}>
          <div className={styles.sectionTitle}><h3>اجرای اخیر</h3><button type="button" onClick={() => void load()} disabled={loading}>بازخوانی</button></div>
          {loading ? <p>در حال دریافت اطلاعات...</p> : requests.length ? (
            <div className={styles.tableWrap}>
              <table>
                <thead><tr><th>زمان</th><th>منبع اجرا</th><th>نسخه</th><th>وضعیت</th><th>تعداد</th></tr></thead>
                <tbody>{requests.slice(0, 10).map((item) => (
                  <tr key={item.id}>
                    <td>{formatDate(item.created_at)}</td>
                    <td>{item.trigger_label}</td>
                    <td>{fa.format(item.context_version || 0)}</td>
                    <td>{item.status_label}</td>
                    <td>{fa.format(Number(item.metadata?.candidate_count || 0))}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p>هنوز اجرای تحلیلی ثبت نشده است.</p>}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionTitle}><h3>نتایج اخیر</h3><span>{fa.format(drafts.length)} نتیجه</span></div>
          {drafts.length ? <div className={styles.draftList}>{drafts.slice(0, 30).map((draft) => (
            <article key={draft.id} className={styles.draftCard}>
              <div className={styles.draftHeading}>
                <div><h4>{draft.notice_title}</h4><span>{formatDate(draft.analyzed_at)} · {draft.priority_label}</span></div>
                <div className={styles.score}><b>{fa.format(draft.score)}</b><small>از ۱۰۰</small></div>
              </div>
              <p><b>تناسب:</b> {draft.fit_for_pdp}</p>
              <p><b>دلیل:</b> {draft.reason}</p>
              <p><b>اقدام پیشنهادی:</b> {draft.recommended_action}</p>
              <div className={styles.draftFooter}>
                <span className={draft.is_recommended ? styles.recommended : styles.notRecommended}>
                  {draft.is_recommended ? "پیشنهاد شده" : "پیشنهاد نشده"}
                </span>
                <span>{draft.review_status_label}</span>
                {draft.review_status === "ai_draft" && <div className={styles.actions}>
                  <button type="button" onClick={() => reviewDraft(draft, "reviewed")} disabled={Boolean(busy)}>بازبینی شد</button>
                  <button type="button" onClick={() => reviewDraft(draft, "published")} disabled={Boolean(busy)}>انتشار</button>
                  <button type="button" onClick={() => reviewDraft(draft, "rejected")} disabled={Boolean(busy)} className={styles.reject}>رد</button>
                </div>}
              </div>
            </article>
          ))}</div> : <p>هنوز Draft تحلیلی تولید نشده است.</p>}
        </section>
      </section>
    </div>
  );
}
