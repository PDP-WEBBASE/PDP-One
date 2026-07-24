"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import styles from "./analysis-context-manager.module.css";

type Section = "prompts" | "keywords" | "company" | "versions";
type AttachmentCategory = "prompt_reference" | "keywords" | "company_profile" | "qualifications" | "resume" | "other";

type Attachment = {
  id: string;
  category: AttachmentCategory;
  category_label: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  download_url: string;
  created_at: string;
};

type ContextSnapshot = {
  id: string;
  version: number;
  status: "draft" | "active" | "retired";
  status_label: string;
  is_locked: boolean;
  role_text: string;
  base_instructions: string;
  analysis_prompt: string;
  company_profile: Record<string, unknown>;
  qualifications: unknown[];
  keywords: { active?: unknown[]; excluded?: unknown[]; [key: string]: unknown };
  experience_summary: unknown[];
  component_versions: Record<string, number>;
  changed_components: string[];
  content_hash: string;
  attachments: Attachment[];
  activated_at: string | null;
  activated_by_username: string;
  created_at: string;
  updated_at: string;
};

type FormState = {
  roleText: string;
  baseInstructions: string;
  analysisPrompt: string;
  companySummary: string;
  qualifications: string;
  activeKeywords: string;
  excludedKeywords: string;
  experienceSummary: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const PROCUREMENT_API = `${API_BASE}/procurement`;
const fa = new Intl.NumberFormat("fa-IR");
const faDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const sectionLabels: Record<Section, string> = {
  prompts: "نقش و Prompt",
  keywords: "کلیدواژه‌ها",
  company: "پروفایل، صلاحیت و رزومه",
  versions: "نسخه‌ها و فعال‌سازی",
};

const categoryLabels: Record<AttachmentCategory, string> = {
  prompt_reference: "مرجع نقش و Prompt",
  keywords: "کلیدواژه‌ها",
  company_profile: "پروفایل شرکت",
  qualifications: "صلاحیت‌ها",
  resume: "رزومه و سوابق",
  other: "سایر",
};

const emptyForm: FormState = {
  roleText: "",
  baseInstructions: "",
  analysisPrompt: "",
  companySummary: "",
  qualifications: "",
  activeKeywords: "",
  excludedKeywords: "",
  experienceSummary: "",
};

function collection<T>(payload: T[] | { results?: T[] }): T[] {
  return Array.isArray(payload) ? payload : payload.results || [];
}

function lines(value: unknown[]): string {
  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "title" in item) return String((item as { title?: unknown }).title || "");
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

function listFromText(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formFromSnapshot(snapshot: ContextSnapshot | null): FormState {
  if (!snapshot) return emptyForm;
  const summary = snapshot.company_profile?.summary;
  return {
    roleText: snapshot.role_text || "",
    baseInstructions: snapshot.base_instructions || "",
    analysisPrompt: snapshot.analysis_prompt || "",
    companySummary: typeof summary === "string" ? summary : "",
    qualifications: lines(snapshot.qualifications || []),
    activeKeywords: lines((snapshot.keywords?.active || []) as unknown[]),
    excludedKeywords: lines((snapshot.keywords?.excluded || []) as unknown[]),
    experienceSummary: lines(snapshot.experience_summary || []),
  };
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : faDate.format(date);
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
    return Object.entries(payload)
      .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(" ") : String(value)}`)
      .join(" | ");
  } catch {
    return `خطای HTTP ${response.status}`;
  }
}

export default function AnalysisContextManager({
  initialSection,
  onClose,
}: {
  initialSection: Section;
  onClose: () => void;
}) {
  const [section, setSection] = useState<Section>(initialSection);
  const [snapshots, setSnapshots] = useState<ContextSnapshot[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const active = useMemo(() => snapshots.find((item) => item.status === "active") || null, [snapshots]);
  const draft = useMemo(() => snapshots.find((item) => item.status === "draft") || null, [snapshots]);
  const selected = useMemo(
    () => snapshots.find((item) => item.id === selectedId) || draft || active || snapshots[0] || null,
    [snapshots, selectedId, draft, active],
  );

  const load = useCallback(async (preferredId = "") => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${PROCUREMENT_API}/analysis-contexts/?ordering=-version`, {
        credentials: "include",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await responseError(response));
      const items = collection<ContextSnapshot>(await response.json()).sort((a, b) => b.version - a.version);
      setSnapshots(items);
      const preferred = items.find((item) => item.id === preferredId);
      const currentDraft = items.find((item) => item.status === "draft");
      const currentActive = items.find((item) => item.status === "active");
      const next = preferred || currentDraft || currentActive || items[0] || null;
      setSelectedId(next?.id || "");
      setForm(formFromSnapshot(next));
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "دریافت تنظیمات تحلیل انجام نشد.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function notify(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 5000);
  }

  function selectSnapshot(snapshot: ContextSnapshot) {
    setSelectedId(snapshot.id);
    setForm(formFromSnapshot(snapshot));
    setEditing(false);
  }

  async function createDraft() {
    setBusy("draft");
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis-contexts/create-draft/`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify(active ? { source_snapshot: active.id } : {}),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const created = (await response.json()) as ContextSnapshot & { reused_draft?: boolean };
      await load(created.id);
      setForm(formFromSnapshot(created));
      setEditing(true);
      notify(created.reused_draft ? "نسخه پیش‌نویس موجود برای ویرایش باز شد." : `نسخه ${fa.format(created.version)} برای ویرایش ساخته شد.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ساخت نسخه ویرایشی انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  async function saveDraft() {
    if (!selected || selected.status !== "draft") return;
    setBusy("save");
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis-contexts/${selected.id}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({
          role_text: form.roleText,
          base_instructions: form.baseInstructions,
          analysis_prompt: form.analysisPrompt,
          company_profile: { ...(selected.company_profile || {}), summary: form.companySummary },
          qualifications: listFromText(form.qualifications),
          keywords: {
            ...(selected.keywords || {}),
            active: listFromText(form.activeKeywords),
            excluded: listFromText(form.excludedKeywords),
          },
          experience_summary: listFromText(form.experienceSummary).map((title) => ({ title })),
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const updated = (await response.json()) as ContextSnapshot;
      await load(updated.id);
      notify("نسخه پیش‌نویس ذخیره و دوباره قفل شد.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ذخیره نسخه انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  async function activateDraft() {
    if (!selected || selected.status !== "draft") return;
    if (!window.confirm(`نسخه ${selected.version} فعال و نسخه قبلی بازنشسته شود؟`)) return;
    setBusy("activate");
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis-contexts/${selected.id}/activate/`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": token },
        body: "{}",
      });
      if (!response.ok) throw new Error(await responseError(response));
      const activated = (await response.json()) as ContextSnapshot;
      await load(activated.id);
      notify(`نسخه ${fa.format(activated.version)} فعال شد.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "فعال‌سازی نسخه انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  async function uploadFile(category: AttachmentCategory, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selected || selected.status !== "draft") return;
    setBusy(`upload-${category}`);
    setError("");
    try {
      const token = await csrfToken();
      const data = new FormData();
      data.set("context_snapshot", selected.id);
      data.set("category", category);
      data.set("file", file);
      const response = await fetch(`${PROCUREMENT_API}/analysis-context-files/`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", "X-CSRFToken": token },
        body: data,
      });
      if (!response.ok) throw new Error(await responseError(response));
      await load(selected.id);
      notify(`فایل «${file.name}» بارگذاری شد.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "بارگذاری فایل انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  async function deleteFile(attachment: Attachment) {
    if (!selected || selected.status !== "draft") return;
    if (!window.confirm(`فایل «${attachment.original_name}» حذف شود؟`)) return;
    setBusy(`delete-${attachment.id}`);
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${PROCUREMENT_API}/analysis-context-files/${attachment.id}/`, {
        method: "DELETE",
        credentials: "include",
        headers: { Accept: "application/json", "X-CSRFToken": token },
      });
      if (!response.ok) throw new Error(await responseError(response));
      await load(selected.id);
      notify("فایل از نسخه پیش‌نویس حذف شد.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "حذف فایل انجام نشد.");
    } finally {
      setBusy("");
    }
  }

  function field(label: string, key: keyof FormState, rows: number, hint?: string) {
    return <label className={styles.field}>
      <span>{label}</span>
      <textarea rows={rows} value={form[key]} readOnly={!editing} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
      {hint && <small>{hint}</small>}
    </label>;
  }

  function filePanel(category: AttachmentCategory, accept: string) {
    const items = (selected?.attachments || []).filter((item) => item.category === category);
    return <section className={styles.filePanel}>
      <div className={styles.filePanelHead}>
        <strong>{categoryLabels[category]}</strong>
        {editing && selected?.status === "draft" && <label className={styles.uploadButton}>
          {busy === `upload-${category}` ? "در حال بارگذاری…" : "افزودن فایل"}
          <input type="file" accept={accept} disabled={busy !== ""} onChange={(event) => void uploadFile(category, event)} />
        </label>}
      </div>
      {items.length ? <div className={styles.fileList}>{items.map((attachment) => <div key={attachment.id}>
        <span><b>{attachment.original_name}</b><small>{fa.format(Math.ceil(attachment.size_bytes / 1024))} کیلوبایت</small></span>
        <span className={styles.fileActions}>
          <a href={attachment.download_url} target="_blank" rel="noreferrer">دریافت</a>
          {editing && selected?.status === "draft" && <button disabled={busy !== ""} onClick={() => void deleteFile(attachment)}>حذف</button>}
        </span>
      </div>)}</div> : <p className={styles.emptyText}>فایلی در این دسته ثبت نشده است.</p>}
    </section>;
  }

  return <div className={styles.backdrop} dir="rtl" role="dialog" aria-modal="true">
    <section className={styles.modal}>
      <header className={styles.header}>
        <div>
          <small>تنظیمات واقعی و نسخه‌بندی‌شده تحلیل</small>
          <h2>{sectionLabels[section]}</h2>
          <p>{selected ? `نسخه ${fa.format(selected.version)} · ${selected.status_label}` : "هنوز نسخه‌ای ثبت نشده است."}</p>
        </div>
        <button className={styles.closeButton} onClick={onClose} aria-label="بستن">×</button>
      </header>

      <nav className={styles.tabs}>{(Object.keys(sectionLabels) as Section[]).map((id) => <button key={id} className={section === id ? styles.activeTab : ""} onClick={() => setSection(id)}>{sectionLabels[id]}</button>)}</nav>

      {message && <div className={styles.success}>{message}</div>}
      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.toolbar}>
        <div className={styles.versionStatus}>
          {active && <span className={styles.activeBadge}>فعال: نسخه {fa.format(active.version)}</span>}
          {draft && <span className={styles.draftBadge}>پیش‌نویس: نسخه {fa.format(draft.version)}</span>}
          {!draft && <span className={styles.lockedBadge}>اطلاعات فعال قفل است</span>}
        </div>
        <div className={styles.toolbarActions}>
          {!draft && <button className={styles.secondary} disabled={busy !== ""} onClick={() => void createDraft()}>{busy === "draft" ? "در حال ساخت…" : "ویرایش و ساخت نسخه جدید"}</button>}
          {draft && !editing && <button className={styles.secondary} onClick={() => { setSelectedId(draft.id); setForm(formFromSnapshot(draft)); setEditing(true); }}>ویرایش نسخه پیش‌نویس</button>}
          {draft && editing && <button className={styles.primary} disabled={busy !== ""} onClick={() => void saveDraft()}>{busy === "save" ? "در حال ذخیره…" : "ذخیره و قفل"}</button>}
          {draft && <button className={styles.activate} disabled={busy !== "" || editing} onClick={() => void activateDraft()}>{busy === "activate" ? "در حال فعال‌سازی…" : "فعال‌سازی نسخه"}</button>}
        </div>
      </div>

      <main className={styles.body}>
        {loading && <p>در حال دریافت نسخه‌های واقعی…</p>}
        {!loading && section === "prompts" && <div className={styles.grid}>
          {field("نقش تخصصی ChatGPT", "roleText", 5)}
          {field("دستورهای پایه", "baseInstructions", 6)}
          {field("Prompt مشترک تحلیل مناقصات و استعلامات", "analysisPrompt", 9)}
          {filePanel("prompt_reference", ".txt,.md,.pdf,.doc,.docx")}
        </div>}

        {!loading && section === "keywords" && <div className={styles.gridTwo}>
          {field("کلیدواژه‌های فعال", "activeKeywords", 14, "هر کلیدواژه در یک خط")}
          {field("کلیدواژه‌های حذف یا احتیاط", "excludedKeywords", 14, "هر عبارت در یک خط")}
          <div className={styles.wide}>{filePanel("keywords", ".txt,.md,.csv,.xls,.xlsx")}</div>
        </div>}

        {!loading && section === "company" && <div className={styles.grid}>
          {field("پروفایل خلاصه شرکت", "companySummary", 7)}
          {filePanel("company_profile", ".txt,.md,.pdf,.doc,.docx")}
          {field("صلاحیت‌ها", "qualifications", 10, "هر صلاحیت در یک خط")}
          {filePanel("qualifications", ".txt,.md,.pdf,.doc,.docx,.xls,.xlsx")}
          {field("خلاصه سوابق و تجربیات", "experienceSummary", 10, "هر سابقه در یک خط")}
          {filePanel("resume", ".txt,.md,.pdf,.doc,.docx")}
        </div>}

        {!loading && section === "versions" && <div className={styles.versionArea}>
          <div className={styles.versionCards}>
            {snapshots.map((snapshot) => <button key={snapshot.id} className={`${styles.versionCard} ${selected?.id === snapshot.id ? styles.selectedVersion : ""}`} onClick={() => selectSnapshot(snapshot)}>
              <span><b>نسخه {fa.format(snapshot.version)}</b><small>{snapshot.status_label}</small></span>
              <span><small>ثبت: {formatDate(snapshot.created_at)}</small><small>فعال‌سازی: {formatDate(snapshot.activated_at)}</small></span>
              <span><small>تغییرات: {snapshot.changed_components.length ? snapshot.changed_components.join("، ") : "بدون تغییر ثبت‌شده"}</small></span>
            </button>)}
          </div>
          {selected && <article className={styles.versionDetail}>
            <h3>جزئیات نسخه {fa.format(selected.version)}</h3>
            <dl>
              <div><dt>وضعیت</dt><dd>{selected.status_label}</dd></div>
              <div><dt>ثبت‌کننده فعال‌سازی</dt><dd>{selected.activated_by_username || "—"}</dd></div>
              <div><dt>آخرین ویرایش</dt><dd>{formatDate(selected.updated_at)}</dd></div>
              <div><dt>Hash محتوا</dt><dd className={styles.hash}>{selected.content_hash}</dd></div>
              <div><dt>تعداد فایل‌ها</dt><dd>{fa.format(selected.attachments.length)}</dd></div>
            </dl>
          </article>}
        </div>}
      </main>
    </section>
  </div>;
}
