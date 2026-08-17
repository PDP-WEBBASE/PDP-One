# PDP One — Canonical Timeline

This timeline preserves historical evolution. A later event may supersede an earlier state without deleting it.

## Historical imported / Transfer v10 lineage

### 2026-07-20 — Stable baseline / BACKLOG-001
- Historical stable deployment commit: `cf1bcc40a0290d05fb31cce606f2521c4b9341f5`.
- Final backup: `PDP-One-final-Backup-20260720-172949`.
- Isolated restore verification established as part of the historical guarded release process.
- Source: Transfer v10 implementation/deployment history.

### 2026-07-21 — Portable backup capability
- Portable encrypted backup capability verified as DPAPI-independent.
- Isolated restore and copy-hash verification recorded.
- Historical portable payload: `PDP-One-Portable-Backup-20260721-223550.pdpone`.
- Historical archive path included `D:\BackUp PDP-0NE-14050429-01`.
- Source: EVD-010, backup register, portable backup report.

### 2026-07-22 — Windows startup/connectivity hotfix and connector capture work
- Windows stable startup/self-healing work replaced earlier manual CONNECT-CHATGPT/token-changing startup concepts.
- Hotfix handoff documented limited self-healing, DNS/connectivity diagnostics, stable startup task behavior, MCP/Tailscale checks and deployment safety.
- Early deployment work exposed defects in health/version proof, rollback/diagnostics handling and startup reliability.
- Connector captures for external tender/inquiry sources progressed.
- Source: hotfix handoff, restart guide, diagnostics, Transfer chronology.

### 2026-07-23 — Connector development and live-source testing
- Hezareh, Pars Namad and SETAD extraction/capture work progressed.
- Modular source/type connector architecture continued.
- Source: Transfer chronology and connector evidence.

### 2026-07-24 — Procurement V13–V24 operational debugging
- API/DB integration, session handling, polling, deployment-agent bootstrap, disk recovery and installation/version proof were debugged.
- V18 source/download deployment attempted and failed; commit `e8322e42...`.
- V20 timeout/fallback deployment succeeded; commit `8b15854a...`.
- V21 Nginx/API-route health changes succeeded; commit `e067d5fc...`.
- V22 session/poll deployment failed during backend image prebuild; commit `27d1a611...`.
- V23 retry was later proven not installed despite a healthy-looking state; commit `f1cd7baa...`.
- V24 introduced build-marker/browser proof; commit `db70cc70...`; accepted.
- Safe Docker cleanup/WSL compaction work explicitly avoided volume prune.
- Lessons: Nginx-only `/healthz` is insufficient; whole-page polling destabilized UI; health does not by itself prove the intended bundle is installed.
- Source: deployment register, V18/V22/V23/API-route/Docker/WSL diagnostics.

### 2026-07-25 — V25, release and connector acceptance
- V25 fast initial load accepted on Windows exact commit `ee5c83aeeced74f7a00ed1aaf39305e3413dfbac`.
- Deployment: `procurement-v25-fast-load-ee5c83ae-20260725`.
- Build ID: `procurement-fast-initial-v25-20260725`.
- V25 backup: `PDP-One-final-Backup-20260725-003429`; post-release backup later recorded as `PDP-One-final-Backup-20260725-075733`.
- Full Windows restart/fast-load acceptance passed.
- Release `v1.1.0-trial` published at `02f28984b68c0e8563f4bc6f789cf0aaeec1c2b6`.
- Connector acceptance `connector-acceptance-v2-final-20260725` completed with warnings: five tested connectors, 15 pages, 510 records seen, zero failed records; Pars Namad tenders disabled.
- Historical connector conditions included Hezareh date warnings and public-list-only SETAD acceptance constraints.
- Source: v10 release/V25 baseline, connector acceptance report.

### 2026-07-31 — Transfer Package v10 freeze
- Historical GitHub main: `f2f38d382af6bf92302d9a2169c439d4e0f94523`.
- Release commit remained `02f28984...`; Windows runtime remained `ee5c83ae...`; these were explicitly three distinct baselines.
- Live read-only snapshot: PostgreSQL connected, 9 contracts, 3 receivables, 0 analysis drafts.
- PR22, PR23 and PR24 were all still open/draft, creating a connector-acceptance configuration-management gap.
- Transfer v10 generated under documentation freeze with no operational mutation.
- Package states its historical imported chat context is summarized rather than reconstructed line-by-line.
- Transfer v10 identified canonical reconciliation of PR22–24 as the next action at that time.
- Source: Transfer README, Executive Summary, Decision Log, Chronology, Evidence Index.

## Post-transfer continuation lineage

### 2026-08-01 — MCP startup self-heal PR45
- PR45 opened: `hotfix/mcp-startup-self-heal-20260801`, head `1f8b8bea...`.
- It documented a Windows-startup MCP restart-loop/import failure and proposed limited MCP self-heal behavior without token rotation/volume mutation.
- PR remained draft/open and is still open as of the 2026-08-17 bootstrap; it must not be assumed current production lineage.

### 2026-08-02 — Deployment coordination PR46 and continuation work
- PR46 opened: `fix/deployment-coordination-lock-20260802`, head `fbd431ba...`, addressing the historical deployment/startup/disk-cleanup race with a deployment marker/mutex and image pinning concepts.
- It remains open as of 2026-08-17 and is not automatically considered merged/current.
- Historical continuation work later established a development-fast workflow and exact-image/deployment practices; current decisions supersede the heavier routine backup gate for normal development-fast changes.
- A one-time full pending analysis task was started around this period and the persistent run later visible as `755ad573...` began on 2026-08-03.

### 2026-08-03 — Persistent full-pending procurement analysis run begins
- Active run ID: `755ad573-0bdd-4437-9b3e-0f6f09a64b96`.
- Stored configuration included `include_expired=true`, `include_previously_analyzed=true`, shard 250, deep batch 25, stored parallel workers 4.
- Over time this run accumulated checkpoints and was later upgraded by code to adaptive admission/newest-first semantics without cancel/restart.

## Current-chat implementation wave — 2026-08-11/12

### PR54 — Recommendation source of truth
- User reported recommendation/list visibility inconsistencies across Tender and Inquiry.
- Root cause: UI/endpoint relied on stale compatibility field `ProcurementNotice.is_recommended` and mixed general/recommended list semantics.
- Solution: `recommended-notices` based on latest effective valid `NoticeAnalysisDraft`; rejected/latest non-recommended draft removes effective recommendation. General lists restricted to recent 3 days; Recommended retains complete history.
- Exact head: `5b0e734a27abe3d77b091212dd5e02e4de214da3`.
- CI/frontend/backend/immutable images: success.
- Merge: `833dc8e3a72bdd53f46ff242bab5dd0be680822e`.
- Historical pre-deploy data baseline recorded 595 analysis drafts / 150 AI recommendations.

### PR55 — Management toolbar and selected workflow
- Floating management controls replaced by a responsive management toolbar.
- Selected Tender/Inquiry rows gained remove-from-selected and documents/send actions.
- Case removal preserves the underlying Notice/analysis and is blocked after submission/document-history conditions.
- Submission-document infrastructure used for multi-file upload and transition to Submitted after successful selected-file upload.
- Exact head: `2037146250064b04fc6d30f8227526ad83acbd54`.
- Deployment: `procurement-ui-v23-20371462-20260811`, succeeded/healthy; independent health healthy.
- Merge: `cd306a354b84269bb5b7d8e0581b7bfad3dc14dc`.
- Post-deploy data: 10 contracts / 3 receivables / 595 drafts / 150 AI recommendations unchanged.

### PR56 — Tabs, Timeout fix and Direct Opportunity selected actions
- Analysis controls moved into management tools; management tools became a top-level workspace tab; old management tab renamed extraction/analysis tools.
- Root cause of archive Timeout: selected-action layer scanned/paginated the full Tender/Inquiry archive to join Cases.
- Fix: load bounded selected Case stages plus specific Notice details; avoid full-archive scan.
- Direct Opportunities received selection and selected workflow using existing submission-document infrastructure.
- Exact head/deployed commit: `1837bdc7aafe891b7f6ca99d2664f1b28e0376ef`.
- Deployment: `procurement-v24-1837bdc7-20260811`.
- Deploy request `cb08e7ff-...`; independent health request `e3b7bceb-...`; succeeded/healthy.
- Merge: `7ab4db6939c4e6b0a5e75beae8289bebaed00770`.
- MCP/Connected App briefly flapped during restart; no duplicate deploy was issued.

### PR57 — Results, zero-file submission, Direct workflow and human recommendation dismissal
- Submitted Tender/Inquiry/Direct Opportunity gained `ثبت نتیجه`; final states display in Results.
- Submission without attachment became valid; existing file upload path retained for selected files.
- Direct Opportunity `Recommended` tab removed: All → Selected → Submitted → Result.
- Tender/Inquiry recommendation view gained human `حذف از پیشنهادی`; latest effective AI recommendation is rejected/audited without deleting the Notice.
- Exact head/deployed commit: `9e1a48c5029b77be43c9dd31cc25deb839d3bdd0`.
- Deployment `procurement-v25-9e1a48c5-20260812`; request `ffe85f05-...`; independent health `7b924f98-...`; succeeded/healthy.
- Merge: `f531471d67111f7cf52ac05fad84c06769732e0d`.

### PR58 — Adaptive admission, newest-first and Hyper Turbo foundation
- User required analysis throughput high enough not to fall behind 4–5k new notices/day and wanted backlog processing to prioritize newest notices.
- Investigation discovered active run behaved like an old snapshot for notices entering after run start.
- Backend changed to admit fresh eligible notices into the active run and claim them `newest_first` (last-seen/publication ordering as implemented).
- Claims remain atomic/leased; drafts require human review.
- Live proof after code activation admitted **21,311** notices outside the old frozen snapshot.
- Historical run snapshot after admission: total **43,944**, completed **6,670**, remaining **37,261**.
- First deployment record `analysis-hyper-turbo-d2d70c67-20260812` ended failed while independent runtime health/code proof was healthy; merge was withheld at that point.
- Controlled redeploy of exact head `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f` as `analysis-hyper-turbo-d2d70c67-20260812-r2` succeeded/healthy.
- Deployment request: `49dc7f7e-a978-41fc-a869-c8f7f5c1cefd`; independent health request `9e7643f5-...` succeeded/healthy.
- PR58 merge: `b99dfedc43c64c00b536bcb625d62499d7f1a4c3`.

### Hyper Turbo scheduled-lane creation
- Desired policy created eight hourly logical lanes.
- Historical intended capacity policy: >=20k 8 lanes; 10k–19,999 6 lanes; 5k–9,999 4 lanes; 1k–4,999 2 lanes; <1k reduced primary lane.
- Only Lane 1 may create an incremental run if none exists; auxiliary lanes must not cancel/restart the run.
- Each lane uses bounded claims, AI Draft import and human-review safeguards; no financial/contract side effects.
- Important: desired creation history does not guarantee later enabled state.

## 2026-08-17 — Canonical project-memory bootstrap

### Read-only audit
- User approved `PDPONE START` as the sole operational activation keyword and activated the memory migration.
- GitHub main verified at `b99dfedc43c64c00b536bcb625d62499d7f1a4c3`.
- No pre-existing canonical `PDP-ONE-START-HERE`, Manifest or Current State files found.
- No pre-existing active `pdp-active-work` issue found.
- Open PR45/46 discovered and recorded as stale/open historical operational work.
- Runtime verified: PostgreSQL connected; 10 contracts; 3 receivables; 1,219 analysis drafts; deployment queue healthy with arbitrary shell disabled.
- Exact deployed commit reverified from request `49dc7f7e...`: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`, deployment `analysis-hyper-turbo-d2d70c67-20260812-r2`.
- Active run snapshot now: total **51,632**, completed **12,326**, remaining **39,293**; `newest_first` and adaptive admission remain active. This new snapshot does not replace historical snapshots.
- Transfer v10 ZIP reverified: 69/69 extracted files; SHA-256 `fac51cd0ee4999b53fcae613c0ca6186a7e3fdcb4e7f99f1c0e606b71a62fff4`; 68/68 internal checksum-covered files PASS.
- Company résumé verified as a 66-page PDF; representative pages rendered and text extraction available for derived company knowledge.
- Textual secret-like scan found no common credential patterns in package text.

### Automation Drift discovered
- Live ChatGPT Automations: lanes 1,2,4,6,7,8 enabled; lanes 3 and 5 disabled.
- This conflicts with historical eight-lane desired state for >20k backlog.
- Drift is recorded; no Automation mutation was performed during memory bootstrap.

### Governance session opened
- Session Issue #59: `PDP-SESSION-20260817-PROJECT-MEMORY-BOOTSTRAP`.
- Branch: `docs/project-memory-bootstrap-20260817`.
- Scope: project-memory/governance/docs/automation specification only; no DB/runtime mutation.
- Canonical memory creation started.

## 2026-08-17 — MCP end-to-end stability incident resolved (Session #61 / PR66)

- Intermittent real Connected MCP failures were reproduced while web/API/PostgreSQL remained healthy.
- PR66 introduced service/Docker/token-bound MCP health, Streamable HTTP proxy hardening, exact `mcp==1.28.1`, stateful JSON POST responses, and non-disruptive handling of public-only MCP degradation.
- First accepted-health deployment `cf99960c...` still reproduced the intermittent error; runtime acceptance failed and merge was withheld.
- Second deployment `f364f056...` (request `2dcba6e7-3371-48ec-b1cf-12ef1e2d8f23`) was healthy but a multi-minute Connected MCP outage occurred; acceptance failed and merge remained blocked.
- Third exact deployed head `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`, deployment `mcp-stability-hysteresis-ee4095e2-20260817`, request `a05290f2-a168-483d-a26c-7781eff977b7`, succeeded/healthy; independent health `457e3555-3fab-44f3-8c8f-f29e4362f084` succeeded/healthy.
- Final acceptance crossed >11 minutes and more than two five-minute watchdog periods, with recorded 8/8 plus 6/6 additional Connected MCP reads and no reproduced network error outside deployment restart.
- PostgreSQL remained connected; contracts=10 and receivables=3 remained unchanged; deployment queue remained pending=0.
- PR66 merged as `7cc0c025cec69dbe161acb56cedf832f63867c38`; the exact deployed application remains the accepted PR head `ee4095e2...`, not the merge SHA.
- Permanent evidence: `history/incidents/INC-2026-08-17-MCP-INTERMITTENT-CONNECTION.md` and `history/sessions/2026-08-17-mcp-end-to-end-stability.md`.
