# PDP One — Decision Register

This register preserves decisions across chats. Old decisions are not erased; they are marked Historical or Superseded when later decisions replace them.

## Historical Transfer v10 decisions

### DEC-001 — Windows trial architecture
- Decision: Docker/PostgreSQL/Nginx/Tailscale on the Windows trial host.
- Status: **Active architecture lineage / historical decision**.
- Source: Transfer v10 `03-PDPOne-Decision-Log.md`, EVD-007.

### DEC-002 — Authentication
- Decision: One-step login is sufficient; no 2FA; automatic logout disabled for now.
- Status: **Active unless a later explicit user decision changes it**.
- Source: Transfer v10 DEC-002.

### DEC-003 — Connector modularity
- Decision: Separate connector modules by source and notice type.
- Status: **Active**.
- Reason: blast-radius isolation and independent repair.

### DEC-004 — Pars Namad tenders
- Decision: disable `parsnamad_tenders` while the tender route exposes inquiry content.
- Status: **Active product decision unless source is re-accepted through change control**.

### DEC-005 — Initial extraction window
- Decision: initial extraction covers today plus one previous day.
- Status: **Historical/current extraction policy lineage**; verify current connector settings before changing.

### DEC-006 — Incremental extraction
- Decision: hourly/daily/normal manual extraction stops after confidently reaching existing records.
- Status: **Active policy lineage**.

### DEC-007 — Manual range extraction
- Decision: range extraction scans the full requested date window even after common records are found.
- Status: **Active policy lineage**.

### DEC-008 — Deduplication
- Decision: do not create duplicate notices; preserve updates/history and cross-source links.
- Status: **Active**.

### DEC-009 — AI keyword policy
- Decision: keywords are semantic context/search guidance, not deterministic internal scoring.
- Status: **Active**.
- Supersedes: earlier deterministic-keyword concepts recorded in the contradiction register.

### DEC-010 — Historical deployment gate
- Decision at July baseline: Branch → CI → Preview → exact commit → backup → restore verify → deploy → health/rollback.
- Status: **Superseded for development-fast; retained for historical/standard guarded mode**.
- Superseded by: DEC-014.

### DEC-011 — Production safety
- Decision: no arbitrary shell; no destructive Docker volume operations.
- Status: **Active hard guardrail**.

### DEC-012 — Separate source/runtime baselines
- Decision: GitHub main, release source and operational Windows runtime are distinct identities.
- Status: **Active and strengthened by DEC-015**.

### DEC-013 — July connector-acceptance reconciliation
- Decision: analysis-engine acceptance should wait until overlapping PR22–24 and runtime connector acceptance were reconciled.
- Status: **Historical completed/superseded work item**.
- Historical July state must remain preserved; later project lineage accepted the connector-acceptance implementation and continued beyond this gate.

## Post-transfer / current-project decisions

### DEC-014 — Development-fast change management
- Decision: active fast-development path is **Branch → CI → immutable exact images → exact-commit deploy → short health → merge**.
- Routine per-commit backup/restore verification and per-commit approval are not required in development-fast unless risk/policy specifically demands them.
- No automatic rollback in development-fast.
- Status: **Active**.
- Supersedes: DEC-010 for development-fast only.

### DEC-015 — Exact deployment identity
- Decision: never equate GitHub merge SHA with deployed exact commit. Track PR head, merge commit, build/image identity, deployment ID and runtime exact commit independently.
- Status: **Active hard rule**.

### DEC-016 — Recommendation source of truth (PR54)
- Decision: effective tender/inquiry recommendation is determined by the **latest valid `NoticeAnalysisDraft`**, not stale compatibility field `ProcurementNotice.is_recommended`.
- General tender/inquiry lists show a recent window; Recommended lists show complete effective recommendation history without a date cap.
- Status: **Active implementation**.
- PR54 head: `5b0e734a27abe3d77b091212dd5e02e4de214da3`; merge: `833dc8e...`.

### DEC-017 — Recommended is not Selected
- Decision: AI recommendation remains advisory. Human/company selection is a separate Case/Opportunity workflow decision.
- Status: **Active hard business rule**.

### DEC-018 — Selected record removal semantics (PR55)
- Decision: removing a selected tender/inquiry removes the pre-submission Case only; it does not delete the underlying Notice/analysis. Removal is blocked after submission or when preserved submission documents make deletion unsafe.
- Status: **Active**.

### DEC-019 — Submission documents and send workflow (PR55/PR57)
- Decision: selected records support document management and transition to Submitted; attachments are **not mandatory** for recording submission.
- If files are selected they use the established submission-document flow; zero-file submission may move the Case/Direct Opportunity to submitted without fabricating a document.
- Status: **Active**.

### DEC-020 — Management toolbar and bounded selected lookups (PR56)
- Decision: management functions belong in a responsive management area rather than floating over lists. Selected-action resolution must not paginate through the full tender/inquiry archive; use bounded Case stages and specific Notice details.
- Status: **Active**.

### DEC-021 — Direct Opportunity workflow (PR56/PR57)
- Decision: Direct Opportunities use `All → Selected → Submitted → Result`; the separate Direct `Recommended` tab is removed.
- Direct selection/removal/documents share the existing opportunity/submission infrastructure rather than a parallel storage path.
- Status: **Active**.

### DEC-022 — Result registration (PR57)
- Decision: submitted Tender, Inquiry and Direct Opportunity records can register a result; final Case/opportunity-result state moves them to Results.
- Simple Direct result flow excludes `converted_to_contract` when an actual contract linkage is not provided.
- Status: **Active**.

### DEC-023 — Human dismissal of AI recommendation (PR57)
- Decision: `حذف از پیشنهادی` rejects the current effective AI recommendation through the latest analysis draft/Audit trail; it **does not delete the Notice**. A genuinely newer analysis may recommend the same Notice later.
- Status: **Active**.

### DEC-024 — Persistent analysis run with fresh adaptive admission (PR58)
- Decision: active analysis backlog must not be a permanently frozen start-time snapshot. New eligible notices are admitted into the active persistent run.
- Status: **Active**.

### DEC-025 — Newest-first analysis priority (PR58)
- Decision: when backlog exists, newest notices are claimed first (`last_seen_at`, then publication ordering as implemented), so new tenders/inquiries do not wait behind old backlog.
- Status: **Active**.

### DEC-026 — Atomic multi-lane claims (PR58)
- Decision: concurrent ChatGPT analysis lanes use atomic claim/lease semantics so the same run item is not intentionally claimed by multiple lanes.
- All imports remain AI Drafts requiring human review.
- Status: **Active**.

### DEC-027 — Historical Hyper Turbo capacity design
- Decision at PR58: backlog >=20k targets 8 lanes; 10k–19,999 targets 6; 5k–9,999 targets 4; 1k–4,999 targets 2; below 1k primary lane with reduced claim count. Only Lane 1 may create an incremental run when no run exists; auxiliary lanes must not cancel/restart runs.
- Status: **Desired policy with current live drift**.
- Live 2026-08-17: lanes 3 and 5 disabled, leaving six enabled lanes. Do not silently auto-correct; treat as Automation Drift requiring an activated change session if changed.

### DEC-028 — Do not cancel active long-running analysis for unrelated UI work
- Decision: UI/debug/deployment work must not destroy the active procurement analysis run merely to simplify troubleshooting.
- Status: **Active operational rule**.

## Project-memory governance decisions — 2026-08-17

### DEC-029 — GitHub as canonical project memory/control plane
- Decision: GitHub stores long-term history, active decisions, desired configuration, source registry and multi-chat coordination. ChatGPT's private chat memory is not the project system of record.
- Status: **Active**.

### DEC-030 — Federated live-source model
- Decision: GitHub does not become a raw live replica of Server/PostgreSQL/ChatGPT Automations. Dynamic truth is refreshed from its authoritative source; GitHub stores locators, policy, history and timestamped snapshots.
- Status: **Active**.

### DEC-031 — Historical-source full ingestion
- Decision: Transfer v10 and current-chat evidence must be semantically ingested, not merely archived/indexed. Source evidence and derived canonical knowledge are both preserved with provenance; unavailable raw chat content is recorded as a gap, never invented.
- Status: **Active migration requirement**.

### DEC-032 — Operational activation keyword
- Decision: the only project mutation activation phrase is **`PDPONE START`** at the beginning of the operational request.
- Without it, PDP One work is read-only/advisory.
- Status: **Active hard governance rule**.
- Supersedes: `PDP1 START`, `PDP One Start`, `PDF1` concepts.

### DEC-033 — Standard commands
- Decision: `PDPONE STATUS` performs read-only status/context sync; `PDPONE END` finalizes memory/session closure.
- Status: **Active**.

### DEC-034 — Multi-chat live coordination
- Decision: each operational chat creates/maintains a GitHub Session Issue, declares a soft lock, checks concurrent sessions/PRs at START, PRE-WRITE, PRE-DEPLOY and PRE-MERGE, and records milestone heartbeats.
- Status: **Active**.

### DEC-035 — Automation governance
- Decision: ChatGPT Automation live state must be compared with versioned GitHub desired specs before mutation. Schedule changes are first-class project changes. Important tasks should consume a compact active `AUTOMATION_RUNTIME_CONTEXT`, not re-read the entire historical archive on every run.
- Status: **Active desired governance**.

### DEC-036 — History append, current state refresh
- Decision: history is append/supersede; `CURRENT_STATE` is replaceable cached state sourced from live verification. Failed/ambiguous deployments, rejected proposals and resolved incidents remain visible.
- Status: **Active**.

## Conflict precedence

Latest explicit user decision > verified current operational fact > exact deployment evidence > current GitHub source > active decisions > cached current state > historical archive > transferred context > proposal > inference.

Safety/system constraints still apply above project preferences.
