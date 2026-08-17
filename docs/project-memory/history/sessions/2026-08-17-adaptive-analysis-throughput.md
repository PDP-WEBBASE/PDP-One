# Session — Adaptive high-throughput procurement analysis

- Session ID: `PDP-SESSION-20260817-ADAPTIVE-ANALYSIS-THROUGHPUT`
- Active-work Issue: #80
- PR: #83
- Started: 2026-08-17 22:26 +03:30
- Starting main: `cc5852ac5fa797c98624976881a74764ae13056c`
- Conversation activation: ACTIVE

## Request

Owner approved all phases needed to materially raise analysis throughput so the growing Tender/Inquiry backlog no longer clears at only about 400 records/hour. Desired high-backlog target is 10k–20k analyses/hour where sustainable.

## Live baseline

At session start the authoritative active run reported:

- run: `755ad573-0bdd-4437-9b3e-0f6f09a64b96`
- total: 54,397
- completed: 12,980
- remaining: 41,404
- pending: 23,033
- retry: 18,321
- claimed: 50
- poison: 13
- failed: 0
- `claim_lease_expired`: 18,237
- `newest_first=true`
- `adaptive_admission=true`
- `include_expired=true`
- `include_previously_analyzed=true`

Live ChatGPT Automations showed all eight Hyper Turbo lanes enabled and staggered hourly at minutes 00/05/10/15/20/25/30/35. Each live prompt still limited itself to exactly one 50-item claim per run, producing a theoretical ceiling of about 400/hour.

## Root cause / design finding

PR67 correctly bounded **in-flight** work after an earlier retry storm:

- safe claim size = 50;
- global active claim cap = 400;
- one active package per worker.

The backend already permits the same worker to claim another package after its prior Import clears the active claim. Therefore the present ~400/hour ceiling is mainly an Automation execution-policy bottleneck, not a requirement to enlarge claim size.

A second issue is that the long-lived run was created with `include_previously_analyzed=true`; raw Remaining can therefore overstate the actual catch-up workload when an exact same-content/same-Context result already exists.

## Accepted architecture

### Effective backlog

Publish raw and effective backlog separately. A redundant open `explicit_reanalysis` row can become `SKIPPED` only when an exact valid same-content/same-Context draft or compact result already exists and human review did not request revision. Preserve Notice/result/history and record audit evidence.

### Adaptive package cycles

Keep safe package 50 and global in-flight cap 400. Scale throughput by repeated:

`Claim → semantic analysis → validated Import → next Claim`

The same worker may claim again only after a clean prior Import.

### Adaptive targets

- effective >=50k: 20k/h goal, 8 lanes;
- >=40k: 10k/h, 8 lanes;
- >=20k: 7.5k/h, 8 lanes;
- >=10k: 4k/h, 6 lanes;
- >=5k: 2k/h, 4 lanes;
- >=1k: 1k/h, 2 lanes;
- <1k: 400/h maintenance on lane 1.

Targets are goals, not guarantees. Recent lease-expiry evidence reduces package-cycle allowance through backend backpressure.

### Semantic fast/deep analysis

All claimed records still receive semantic analysis against active Context. Clear non-fit records may use compact structured results. Recommended/urgent/ambiguous/needs-information/high-score records receive detailed/deep review output. Keyword-only deterministic scoring remains prohibited.

### Model execution path

This change retains ChatGPT Scheduled Tasks + PDP One MCP. No separate OpenAI API/provider/server-side model billing path is introduced. A dedicated server model-worker pool, if later required for sustained 10k–20k/h, is a separate architecture/cost/security decision.

## Implementation

Branch: `feat/adaptive-analysis-throughput-20260817`.

Application changes:

- new `backend/procurement/analysis_throughput.py`:
  - exact-valid reanalysis detection/reconciliation;
  - Effective Backlog snapshot;
  - recent throughput/lease health snapshot;
  - adaptive target/backpressure policy;
- `analysis_run_adaptive.py`:
  - records stale-lease events;
  - reconciles safe redundant reanalysis before claiming;
  - preserves one-active-package/worker + global cap;
  - explicitly supports sequential package cycles after clean Import;
- `analysis_statistics.py`:
  - exposes `throughput`, effective remaining and package-cycle claim policy;
- focused throughput-controller tests.

Governance/spec updates:

- `docs/project-memory/procurement/ANALYSIS_ENGINE.md`
- `docs/project-memory/automations/AUTOMATION_REGISTRY.md`
- `docs/project-memory/automations/AUTOMATION_RUNTIME_CONTEXT.md`

## Concurrency

At start, active overlapping runtime work existed:

- #77 / PR78: extraction schedule editor;
- #79: procurement server pagination/lazy loading.

Code scope is split; runtime deployment target overlaps. Resolution is **SPLIT implementation / SEQUENCE deployment**.

PR78 entered a development-fast deployment with exact request:

- deployment ID: `schedule-editor-7973fcb4-20260817`
- request ID: `e68939d4-bacc-48e4-913d-078749a06812`

When Session #80 polled that request during service restart, MCP returned a network error. Per deployment governance, no duplicate deployment was issued. Session #80 must wait for the exact PR78 request to become terminal and re-run PRE-DEPLOY Delta Sync.

## Safety

- active analysis run is not cancelled/restarted;
- no destructive DB/Docker/volume operation;
- no token rotation;
- no claim/content/context integrity bypass;
- no final business decision automation;
- AI Draft + human review preserved.

## Acceptance still required

Before closure:

1. exact-head CI/Memory/immutable images pass;
2. reconcile with current main and concurrent sessions;
3. exact-commit deploy after deployment lock clears;
4. short health and live run-statistics verification;
5. verify Effective Backlog and no unsafe skip behavior;
6. update Hyper Turbo live task prompts only after backend support is live;
7. verify all eight task states/prompts;
8. observe available runtime throughput/lease evidence and report measured sustainable rate without overstating 10k/20k goals;
9. final Project Memory sync, PRE-MERGE Delta Sync, merge and close Issue #80.
