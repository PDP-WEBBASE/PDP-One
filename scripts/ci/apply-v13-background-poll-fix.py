from pathlib import Path

path = Path("app/procurement/ProcurementWorkspaceV13.tsx")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        'import { CSSProperties, FormEvent, useEffect, useMemo, useState } from "react";',
        'import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";',
    ),
    (
        '  const [updatingConnector, setUpdatingConnector] = useState("");\n\n  useEffect(() => {',
        '  const [updatingConnector, setUpdatingConnector] = useState("");\n  const hasLoadedOnce = useRef(false);\n\n  useEffect(() => {',
    ),
    (
        '    async function load() {\n      setMode("loading");\n      try {',
        '    async function load() {\n      if (!hasLoadedOnce.current) setMode("loading");\n      try {',
    ),
    (
        '        setMode("live");\n      } catch (error) {\n        if (!active) return;\n        setMode(error instanceof Error && error.message === "unauthorized" ? "unauthorized" : "error");\n      }',
        '        hasLoadedOnce.current = true;\n        setMode("live");\n      } catch (error) {\n        if (!active) return;\n        if (!hasLoadedOnce.current) {\n          setMode(error instanceof Error && error.message === "unauthorized" ? "unauthorized" : "error");\n        } else {\n          setMessage("به‌روزرسانی پس‌زمینه موقتاً انجام نشد؛ داده‌های قبلی حفظ شدند.");\n        }\n      }',
    ),
    (
        '  const activeRun = extractionRuns.find((run) => run.status === "queued" || run.status === "running");\n  useEffect(() => {\n    if (!activeRun) return;\n    const timer = window.setTimeout(() => setRefresh((value) => value + 1), 5000);\n    return () => window.clearTimeout(timer);\n  }, [activeRun, refresh]);',
        '  const activeRun = extractionRuns.find((run) => run.status === "queued" || run.status === "running");\n  useEffect(() => {\n    if (!activeRun) return;\n    let cancelled = false;\n    const poll = async () => {\n      try {\n        const response = await fetch(`${PROCUREMENT_API}/extraction-runs/${activeRun.id}/`, { credentials: "include", headers: { Accept: "application/json" } });\n        if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) return;\n        const updated = await response.json() as ApiExtractionRun;\n        if (cancelled) return;\n        setExtractionRuns((current) => current.map((run) => run.id === updated.id ? updated : run));\n        if (updated.status !== "queued" && updated.status !== "running") {\n          window.clearInterval(timer);\n          setRefresh((value) => value + 1);\n        }\n      } catch {\n        // Preserve the last successful screen while the next background poll retries.\n      }\n    };\n    const timer = window.setInterval(poll, 5000);\n    return () => {\n      cancelled = true;\n      window.clearInterval(timer);\n    };\n  }, [activeRun?.id]);',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match, got {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)

marker = "به‌روزرسانی پس‌زمینه موقتاً انجام نشد؛ داده‌های قبلی حفظ شدند."
if marker not in text or "window.setInterval(poll, 5000)" not in text:
    raise SystemExit("Required background-poll markers are missing after patch")

path.write_text(text, encoding="utf-8")
