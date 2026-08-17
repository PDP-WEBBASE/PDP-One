# PDP One — Canonical Architecture

This document describes the active architecture lineage while preserving distinctions between historical design intent and live implementation.

## 1. Platform topology

PDP One is a Windows-hosted, containerized web application with a private operational plane and a GitHub-based source/change plane.

Core runtime lineage:

- Windows host
- Rancher Desktop / Docker
- PostgreSQL as the primary structured-data store
- Redis for application/worker infrastructure
- Backend API
- Web frontend
- Celery worker / Celery Beat where configured
- Nginx
- Tailscale/Funnel for remote/public connectivity where enabled
- MCP/ChatGPT connector surface
- local signed-file Deployment Agent

The exact live set must be refreshed from runtime evidence before operational changes.

## 2. Federated control architecture

### GitHub
System of record for:

- source code
- branches/commits/PRs
- CI and immutable image build evidence
- long-term project memory
- active/superseded decisions
- desired configuration
- active change-session coordination
- historical evidence index

### PDP One Runtime / Server
System of record for:

- current business/application data
- PostgreSQL state
- analysis runs and Context
- deployment queue/reports
- connector/extraction live state
- operational service status

### ChatGPT Automations
System of record for:

- currently configured scheduled tasks
- enabled/disabled state
- schedule and actual prompt configuration

GitHub stores the **desired logical Automation specification**. Differences are Automation Drift, not an invitation to overwrite the live Task blindly.

## 3. Data architecture

The Master Design historical source defined a three-layer procurement model that remains part of the active lineage:

1. **Raw source data** — source-specific captured information/evidence.
2. **Normalized data** — canonical Notice/related records after type/date/source normalization and deduplication.
3. **Analysis data** — AI drafts, recommendation/review state, cases/opportunities, decision history and downstream workflow state.

PostgreSQL is the structured system of record. Files are stored separately with metadata linked to business records rather than forcing binary content into relational columns.

GitHub is **not** a replica of PostgreSQL.

## 4. Procurement architecture

Sources historically include:

- SETAD tenders/inquiries
- Hezareh tenders/inquiries
- Pars Namad sources, with Pars Namad tenders disabled under the accepted product decision while that route exposed inquiry-like content

The connector architecture is modular by source and notice type so failures/changes can be isolated.

Deduplication preserves:

- one canonical Notice rather than duplicate business rows
- source occurrences/cross-source links
- update history
- content/hash lineage as applicable

## 5. AI analysis architecture

Active concepts:

- immutable/identified analysis Context snapshot/version/hash
- persistent analysis run
- run items
- atomic claim token + lease
- content/context integrity validation during import
- AI Draft output
- human review
- effective Recommendation distinct from human Selection
- retries/poison handling/checkpoints

PR58 added:

- adaptive admission of fresh eligible notices into an active run
- `newest_first` claim priority
- multi-lane safe claims

The currently running full-pending run was created before these changes and retains stored settings such as `include_expired=true` and `include_previously_analyzed=true`, while the newer queue policy applies to ongoing claiming/admission.

## 6. Recommendation architecture

PR54 made the latest effective valid `NoticeAnalysisDraft` the canonical recommendation source instead of stale `ProcurementNotice.is_recommended` compatibility state.

PR57 added human dismissal of the current AI recommendation through review/Audit semantics without deleting the Notice or its analysis history.

`Recommended` and `Selected` are separate states and authorities.

## 7. Workflow architecture

Current accepted lineage:

### Tender / Inquiry

`All/Recent → AI Recommended → Human Selected → Submitted → Result`

### Direct Opportunity

`All Direct Opportunities → Selected → Submitted → Result`

Submission documents share established storage/metadata infrastructure. Recording submission does not require an attachment; if documents exist they remain part of preserved history.

## 8. Deployment architecture

Current normal development-fast path:

`Branch → CI → immutable exact images → exact-commit deployment → short health → merge`

Rules:

- no routine local app-image builds
- deployment identity is exact commit, not merge SHA
- signed local Deployment Agent; arbitrary shell disabled
- accepted deployment Request ID is followed to terminal state without duplicate writes
- no automatic rollback in development-fast

Historical v10 documented a stronger standard/guarded path with Preview + verified backup/restore. Preserve that history for standard/recovery modes rather than forcing it onto every development-fast change.

## 9. Windows startup/recovery lineage

Historical architecture evolved through:

- manual connectivity/startup concepts
- stable startup task/self-healing
- diagnostics for DNS/Tailscale/MCP/public reachability
- version/build proof beyond Nginx-only health
- deployment/startup/disk-cleanup race investigation

Successful older recovery procedures are historical evidence, not commands to rerun indiscriminately.

## 10. Project-memory/control architecture

Effective 2026-08-17:

- `PDPONE START` gates project mutation.
- Every operational chat performs Context Sync.
- GitHub Session Issues coordinate concurrent work.
- Scope is soft-locked across files/modules/database/runtime/automations.
- Context is refreshed at START, PRE-WRITE, PRE-DEPLOY and PRE-MERGE.
- History is append/supersede; Current State is a refreshable cache.
- Live facts are fetched from their authoritative systems of record.

## 11. Historical Master Design scope

The historical Master Design source described a broader enterprise system roadmap including:

- procurement/opportunities
- business development/CRM
- qualifications/capacity
- contracts
- technical/project management
- finance/receivables
- accounting/integration
- HR
- documents/correspondence
- quality
- risk/claims/change
- knowledge/résumé
- dashboards/KPIs/alerts
- roles/access/audit

These are preserved as design intent/backlog domains. Their presence in the old prompt does not prove every subsystem is implemented today; implementation status must be verified from current code/runtime.
