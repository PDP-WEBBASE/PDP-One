# PDP Session — Analysis Retry Backpressure and Split Statistics

Session ID: `PDP-SESSION-20260817-ANALYSIS-RETRY-STATS`

Active-work Issue: #68

PR: #67

Activation: `PDPONE START`

Started: 2026-08-17 19:59 +03:30

Status: **RUNTIME ACCEPTED — PRE-MERGE FINALIZATION**

## User intent

Continue PR67 to make procurement analysis operationally sustainable: stop the Hyper Turbo retry/lease-expiry storm, keep newest-first analysis, expose exact tender/inquiry/total statistics, deploy the exact candidate only after all gates pass, verify runtime health and data integrity, and merge only after PRE-MERGE coordination.

## START Context Sync

- GitHub main at session start: `be268574fac4a8786664426535f57ce3003f9a35`.
- Candidate branch: `fix/analysis-retry-backpressure-stats-20260817`.
- Candidate head before memory linkage: `9136c42fa2b9374b6c6d3f89cc337a603afe03ee`.
- Active run: `755ad573-0bdd-4437-9b3e-0f6f09a64b96`.
- PostgreSQL: connected.
- Deployment queue: available, no pending deployment at START sync.
- Live analysis baseline: total 53,958; completed 12,890; remaining 41,055; retry 15,394; claimed 3,067; pending 22,594; failed 0.
- System AI review baseline: 1,381 analysis drafts; 420 recommended.

## Diagnosis

The adaptive claim path allowed multiple overlapping packages without per-worker or global backpressure. With large scheduled claims this produced thousands of simultaneous leases; packages that were not imported before lease expiry returned to `retry` as `claim_lease_expired`. Increasing lanes alone therefore increased retry churn rather than real completed throughput.

## Final change scope

- Add per-worker backpressure: a worker with an open, unexpired claim does not receive a second package.
- Add a global active-claim ceiling of 400 items for the active run.
- Enforce a backend safe claim cap of 50 records and a conservative payload ceiling even when an older MCP schema asks for a larger package.
- Preserve atomic claims, adaptive admission and `newest_first` ordering.
- Add exact analysis statistics broken down by `tender`, `inquiry` and `total` for notice population, run population/status, attempted-by-ChatGPT, completed/remaining and AI draft/recommendation visibility.
- Add retry diagnostics including `claim_lease_expired`, active/expired claims and attempts distribution.
- Keep a dedicated read-only statistics endpoint and also append the same statistics as a backward-compatible `statistics` field on the existing current-run and run-status API responses. The already-connected `get_procurement_analysis_run_status` MCP tool can therefore read the new statistics without a ChatGPT MCP schema refresh.
- PR67 has no final change under `services/pdp_mcp/**`.

## Operational mitigation already applied

Before final application deployment, the eight scheduled Hyper Turbo lanes were reduced to at most one claim of 50 records per hourly execution and staggered by five minutes. This conservative mitigation remains compatible with the backend backpressure gate.

## Concurrency and PR66 sequencing

Session #61 / PR66 owned a broad `services/pdp_mcp/**` lock while hardening ChatGPT ↔ PDP One MCP stability. PR67 initially touched `services/pdp_mcp/procurement_analysis_tools.py`, but that file was later restored exactly to `main`; final PR67 file-level overlap with PR66 is zero.

PR66 was deployed and required runtime acceptance over more than two five-minute watchdog periods. PR67 correctly did not deploy over that live candidate. The PR67 session contributed the final read-only acceptance checkpoint: six additional alternating Connected MCP reads succeeded after the >10-minute threshold, with zero `mcp_network_error`, PostgreSQL connected, contracts=10, receivables=3 and deployment queue pending=0.

PR66 was then merged to main as `7cc0c025cec69dbe161acb56cedf832f63867c38` (`Merge PR #66: MCP end-to-end stability hardening`). PR67 was refreshed with a true two-parent merge commit so the candidate contains both the accepted PR66 stability changes and the PR67 analysis changes. The combined pre-final-memory head was `5ba1be16b6a1614d74cb2157d961ff303d53f56a`; the PR diff against the new main remained exactly eight PR67 files.

After Session #61 final Project Memory was merged as PR76 (`991b3a59461ad563671e98025e52a8b4fc5146fb`), PR67 was refreshed again without changing its application code. The post-PR76 head before this final evidence update was `a01b4ace96a5a3482ab8da6e508d7f73939274db`. The delta from the accepted deployed application commit `072a27a5...` to that head was Project Memory/documentation only.

## Deployment history before final combined candidate

- Exact head `c3ed9e74bcb4370dfcbac1673dd341f8d003a39a` passed CI, Memory Governance and immutable Backend/MCP/Web images.
- First deployment record `analysis-retry-stats-c3ed9e74-20260817` ended failed while independent health was healthy; no merge occurred.
- Controlled redeploy `analysis-retry-stats-c3ed9e74-20260817-r2`, request `7dffa4e3-c34f-4452-9393-25e03b27ef46`, succeeded / healthy.
- Independent health request `72c3dbcc-9060-465c-8e12-59debf292cc6` succeeded / healthy.
- That deployment is historical evidence only because PR67 was subsequently hardened and then refreshed on top of merged PR66.

## Accepted final application deployment

The required post-PR66 exact application deployment was completed before final documentation refresh:

- accepted application commit: `072a27a5af74d5170900c61f8162d6c4f6069a9f`;
- deployment ID: `analysis-retry-stats-072a27a5-20260817`;
- deployment request: `8b806cac-4689-4c2b-9abf-67664084494c` → `succeeded / healthy`;
- independent health request: `e51ccca8-4cd9-4f09-8a5e-8dc646407f2f` → `succeeded / healthy`;
- exact-head CI run for `072a27a5...`: `32050466625` → success;
- exact-head immutable images run: `32050466643` → success;
- Memory Governance: success.

No second application deployment is required for subsequent documentation-only synchronization.

## Final live runtime verification

Read-only Connected MCP verification after the accepted deployment confirmed:

- active analysis run remains `755ad573-0bdd-4437-9b3e-0f6f09a64b96`; it was not cancelled or restarted;
- PostgreSQL remains connected;
- contracts remain 10;
- receivables remain 3;
- split statistics are exposed through the existing `get_procurement_analysis_run_status` path;
- `claim_policy.safe_claim_limit = 50`;
- `claim_policy.global_active_claim_cap = 400`;
- `claim_policy.one_active_package_per_worker = true`;
- `priority_policy = newest_first` and adaptive admission remain active;
- snapshot at finalization: total 54,386; completed 12,964; remaining 41,409; pending 23,022; claimed 100; retry 18,287; failed 0; poison 13;
- attempted by ChatGPT: tender 7,737; inquiry 23,627; total 31,364;
- completed: tender 4,676; inquiry 8,288; total 12,964;
- display drafts: tender 582; inquiry 804; total 1,386;
- display recommended: tender 262; inquiry 159; total 421;
- active worker item counts at snapshot: `pdp-hyper-lane-2=50`, `pdp-hyper-lane-3=50`;
- `claim_lease_expired` remained historical backlog at 18,264; the new policy limits new concurrent active claims rather than deleting historical retry state.

These values are timestamped runtime evidence, not permanent counters.

## Concurrency after runtime acceptance

Session #74 / PR75 is a separate frontend-only workstream. A stale PR75 deployment-slot claim was corrected after authoritative recheck showed PR67 runtime acceptance had already completed. PR75 old-base deployment is blocked until PR67 merges; PR75 must then refresh onto the resulting main before its own deployment so it cannot remove the accepted PR67 backend changes.

## Safety constraints preserved

- The active analysis run was not cancelled or restarted.
- Healthy drafts and completed results were not deleted.
- No destructive PostgreSQL/business-data change or schema migration was performed.
- No destructive Docker volume, WSL, Rancher or filesystem recovery action occurred.
- No MCP token rotation or Tailscale identity change occurred.
- No local application-image build occurred.
- No deployment write was duplicated after an accepted Request ID.

## Final merge readiness

At the pre-final-memory head `a01b4ace96a5a3482ab8da6e508d7f73939274db`, PDP One CI run `32051714744`, immutable image run `32051714552`, and Memory Governance run `32051714543` all succeeded. This final evidence update is documentation-only and must rerun exact-head gates before merge; it does not require or justify a second application deployment.

Remaining steps:

1. exact-head gates for this documentation-only evidence commit;
2. PRE-MERGE Delta/Concurrency Sync;
3. merge PR67 only if still clean;
4. close Issue #68 as completed after merge identity is recorded in the Issue.
