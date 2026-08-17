# PDP One — Current State

> **Cached view only. Current State is not a substitute for live verification.**
>
> Refresh relevant sources at START, PRE-WRITE, PRE-DEPLOY and PRE-MERGE.

Last bootstrap verification: **2026-08-17 ~15:44 +03:30**.

## GitHub

- Repository: `PDP-WEBBASE/PDP-One`
- Canonical branch: `main`
- Main commit at bootstrap: `b99dfedc43c64c00b536bcb625d62499d7f1a4c3` — merge of PR58.
- Open PRs at bootstrap: **#45, #46**.
  - #45: historical MCP startup self-heal hotfix; draft; based on old main.
  - #46: historical deployment-coordination race fix; open; based on old main.
  - Treat both as stale/open historical work until explicitly reconciled; do not silently merge or close them.
- Project-memory bootstrap: Issue #59; branch `docs/project-memory-bootstrap-20260817`.

Source: live GitHub connector.

## Runtime / deployment

- PDP One service: reachable.
- PostgreSQL: **connected**.
- Trial mode: `true`.
- Contracts: **10**.
- Receivables: **3**.
- Analysis drafts: **1,219**.
- Analysis review: total 1,219; pending review 1,218; reviewed 1; recommended 339; urgent 19.
- General analysis reports: 9.

Deployment Agent:

- configured: true
- queue available: true
- pending requests: 0
- completed responses: 268
- transport: local signed file queue
- arbitrary shell allowed: **false**
- low disk space: false
- free bytes at observation: 999,762,956,288

Source: live PDP One `get_system_status` and `get_deployment_status`.

## Exact deployed identity

Verified from deployment report request `49dc7f7e-a978-41fc-a869-c8f7f5c1cefd`:

- deployed exact commit: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`
- deployment ID: `analysis-hyper-turbo-d2d70c67-20260812-r2`
- deployment status: `succeeded`
- reported runtime status: `healthy`
- change-management mode: `development_fast`
- routine backup: skipped under development-fast for that deployment

This exact deployed commit is **not** the same object as current main merge commit `b99dfedc...`.

## Procurement analysis live run

Active run:

- run ID: `755ad573-0bdd-4437-9b3e-0f6f09a64b96`
- type: `full_pending_analysis`
- trigger: `manual_chatgpt`
- status: running
- context snapshot: `4612b6a6-ed18-4350-a636-f2a3e4ee26d9`
- context version: 3
- context hash: `67564111125cee3ee86a3f0709e18161fdc2298e1e832ef573999b01598beadf`
- include expired: true
- include previously analyzed: true
- stored export shard size: 250
- stored deep analysis batch size: 25
- stored parallel workers: 4
- started at: 2026-08-03 01:14:51 +03:30

Snapshot at bootstrap:

- total: **51,632**
- completed / AI drafts: **12,326**
- remaining: **39,293**
- pending: 22,603
- claimed: 5,968
- retry: 10,722
- failed: 0
- poison: 13
- recommended: 338 in run counters
- not recommended: 11,988
- needs information: 740
- urgent drafts: 15

Active metadata:

- `draft_only=true`
- `human_review_required=true`
- `priority_policy=newest_first`
- `adaptive_admission=true`

These numbers are a timestamped snapshot and must not overwrite earlier historical snapshots such as 22,633/6,669/15,956 or 43,944/6,670/37,261.

Source: live PDP One `get_procurement_analysis_run_status`.

## Procurement connector acceptance snapshot still exposed by system status

Historical acceptance record `connector-acceptance-v2-final-20260725` remains readable in current system status:

- status: succeeded with warnings
- tested connectors: 5
- disabled: 1
- pages processed: 15
- records seen: 510
- failed records: 0
- Pars Namad tenders: disabled because the source tender route exposed inquiry content
- Hezareh tenders/inquiries: warnings for some unverified dates
- Pars Namad inquiries: accepted with warnings
- SETAD tenders/inquiries: accepted with warnings under public-list constraints

This is an old acceptance execution retained in live state, not proof that source behavior has remained unchanged since July.

## ChatGPT Automations — live observation

Live Hyper Turbo state at bootstrap:

- Lane 1: enabled; hourly
- Lane 2: enabled; hourly
- Lane 3: **disabled**
- Lane 4: enabled; hourly
- Lane 5: **disabled**
- Lane 6: enabled; hourly
- Lane 7: enabled; hourly
- Lane 8: enabled; hourly

Therefore current live state has six enabled Hyper Turbo lanes, while the historical PR58 desired capacity policy described eight lanes for backlog >= 20,000.

Status: **AUTOMATION_DRIFT — unresolved; do not auto-correct without a new activated session/change decision.**

Source: live ChatGPT Automations.

## Active operational policies

- Operational writes require user activation via `PDPONE START`.
- Analysis remains AI Draft + human review.
- Newest notices have priority over old backlog.
- Fresh notices may be adaptively admitted into the active persistent run.
- No arbitrary shell through PDP One.
- No destructive Docker volume operations.
- No local application-image build.
- Development-fast: Branch → CI → immutable exact images → exact-commit deploy → health → merge.
- Merge SHA and deployed exact commit are separate identities.
- Financial/contract changes created by AI are drafts unless an explicitly approved workflow says otherwise.

## Current known conflicts / follow-up

1. Automation drift: lanes 3 and 5 disabled.
2. Old PR45/PR46 remain open and should be reconciled intentionally, not silently.
3. The transfer package's old PR22–24 connector-acceptance uncertainty is historical; later project history indicates connector acceptance PR24/head `884c6e...` became the accepted lineage, but the complete historical resolution must remain in timeline/evidence records rather than rewriting the July snapshot.
4. The active full-pending run still has `include_expired=true` and `include_previously_analyzed=true`; current adaptive admission/newest-first policy mitigates freshness blocking but does not retroactively change the stored run configuration.
