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
- Live bootstrap-day observation: lanes 3 and 5 were disabled, leaving six enabled lanes. This observation is historical/cached; live automation state must be verified before changes.

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

### DEC-032 — Original per-request activation rule
- Earlier decision: `PDPONE START` had to appear at the beginning of each operational request.
- Status: **Superseded**.
- Superseded by: DEC-037.
- Historical reason: protected the project from accidental writes in ordinary chats before Conversation-scoped activation was defined.

### DEC-033 — Standard commands
- Decision: `PDPONE STATUS` performs read-only status/context sync. `PDPONE END` explicitly finalizes applicable memory/session closure and deactivates PDP One mutation mode in that Conversation.
- Status: **Active as amended by DEC-037**.

### DEC-034 — Multi-chat live coordination
- Decision: each material Work Session creates/maintains a GitHub Session Issue, declares a soft lock, checks concurrent sessions/PRs at START/PRE-WRITE/PRE-DEPLOY/PRE-MERGE as appropriate, and records milestone heartbeats.
- Status: **Active, with checkpoints optimized by DEC-039**.

### DEC-035 — Automation governance
- Decision: ChatGPT Automation live state must be compared with versioned GitHub desired specs before mutation. Schedule changes are first-class project changes. Important tasks should consume a compact active `AUTOMATION_RUNTIME_CONTEXT`, not re-read the entire historical archive on every run.
- Status: **Active desired governance**.

### DEC-036 — History append, current state refresh
- Decision: history is append/supersede; `CURRENT_STATE` is replaceable cached state sourced from live verification. Failed/ambiguous deployments, rejected proposals and resolved incidents remain visible.
- Status: **Active**.

### DEC-037 — Conversation-scoped PDPONE activation
- Decision: `PDPONE START` is required **once for each new ChatGPT Conversation**. After successful START Context Sync, that Conversation remains activated for later PDP One requests without repeating the keyword.
- Completing/closing an individual GitHub Work Session/PR does not deactivate the Conversation.
- `PDPONE END` explicitly deactivates the Conversation; a new Conversation always requires a new first `PDPONE START`.
- Status: **Active hard governance rule**.
- Supersedes: DEC-032 per-request activation semantics. The canonical activation phrase itself remains `PDPONE START`; aliases such as `PDP1 START`, `PDP One Start` and `PDF1` remain invalid.

### DEC-038 — Minimal external ChatGPT bootstrap
- Decision: a fresh PDP One Chat needs only a tiny persistent product-level bootstrap: recognize `PDPONE START`, open `PDP-WEBBASE/PDP-One`, read `PDP-ONE-START-HERE.md`, and then rely on GitHub canonical memory/live-source governance.
- The bootstrap must not duplicate project history in ChatGPT Project Instructions.
- Canonical bootstrap text: `PDP-ONE-CHATGPT-BOOTSTRAP.md`.
- Status: **Active design; repository definition implemented**.
- External installation status from Session #72: **Unverified/not programmatically writable with the available tool set**. Do not claim it is installed in ChatGPT Project Instructions until product-level verification exists.

### DEC-039 — Persistent per-Conversation context with Delta Sync
- Decision: initial activation builds one compact Conversation baseline. Subsequent instructions and PRE-WRITE/PRE-DEPLOY/PRE-MERGE checkpoints use lightweight change detection and load only relevant GitHub/Session/PR/Runtime/Automation deltas.
- If nothing relevant changed, reuse cached context. If unrelated changes landed, advance the baseline without loading unrelated history.
- Full canonical reload is exceptional: core governance/schema/architecture changes, unreconcilable baseline drift, very large relevant deltas, or explicit full-resync request.
- Protocol: `docs/project-memory/coordination/DELTA_SYNC_PROTOCOL.md`.
- Status: **Active**.

### DEC-040 — Tiered Memory Retention & Compaction
- Decision: Project Memory uses Tier 0 bootstrap/routing, Tier 1 active operational context, Tier 2 domain summaries, Tier 3 detailed history, and Tier 4 source/evidence archives.
- Routine chats lazy-load deeper tiers. Raw high-volume live datasets, repetitive logs, routine Automation run payloads, Docker/runtime data and large backups must not accumulate in normal Git history.
- Material reasoning/decisions/root causes/identities/evidence remain preserved with provenance; compaction changes the read path, not audit truth.
- Policy: `docs/project-memory/MEMORY_RETENTION_AND_COMPACTION.md`.
- Status: **Active**.

### DEC-041 — Web UI no-reload interaction policy
- Decision: ordinary authenticated PDP One web mutations are **no-reload by default**. Data entry, selection, stage changes, submission/documents, results, settings and management actions update affected local UI state and reconcile targeted data in the background rather than reloading the full page or rebuilding the whole workspace.
- Optimistic UI is preferred when rollback is deterministic; otherwise use the confirmed server response. Pending/error state should remain local so unrelated work can continue, while PostgreSQL/API remains authoritative.
- Current tab, filters, search, scroll and unrelated loaded data should be preserved across ordinary mutations.
- Human Selected remains distinct from AI Recommended: a selected item leaves the actionable Recommended queue while recommendation history remains preserved under DEC-016/DEC-017/DEC-023.
- Allowed hard-navigation/reload exceptions are limited to real route/subsystem navigation, authentication/session recovery, explicit emergency connectivity recovery, or loading a newly deployed client when required.
- ADR: `docs/project-memory/decisions/ADR-041-WEB-UI-NO-RELOAD.md`.
- Status: **Active hard UX/architecture rule**.

## Conflict precedence

Latest explicit user decision > verified current operational fact > exact deployment evidence > current GitHub source > active decisions > cached current state > historical archive > transferred context > proposal > inference.

Safety/system constraints still apply above project preferences.