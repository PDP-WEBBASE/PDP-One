# PDP Session — Analysis Retry Backpressure and Split Statistics

Session ID: `PDP-SESSION-20260817-ANALYSIS-RETRY-STATS`

Active-work Issue: #68

PR: #67

Activation: `PDPONE START`

Started: 2026-08-17 19:59 +03:30

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

## Deployment history before final combined candidate

- Exact head `c3ed9e74bcb4370dfcbac1673dd341f8d003a39a` passed CI, Memory Governance and immutable Backend/MCP/Web images.
- First deployment record `analysis-retry-stats-c3ed9e74-20260817` ended failed while independent health was healthy; no merge occurred.
- Controlled redeploy `analysis-retry-stats-c3ed9e74-20260817-r2`, request `7dffa4e3-c34f-4452-9393-25e03b27ef46`, succeeded / healthy.
- Independent health request `72c3dbcc-9060-465c-8e12-59debf292cc6` succeeded / healthy.
- That deployment is historical evidence only because PR67 was subsequently hardened and then refreshed on top of merged PR66. Final acceptance must use the exact final combined head.

## Safety constraints

- Do not cancel or restart the active procurement analysis run.
- Do not delete healthy drafts or completed results.
- Do not perform destructive PostgreSQL/business-data changes; only ordinary analysis claim/import state transitions of the existing workflow are allowed.
- No destructive Docker volume, WSL, Rancher or filesystem recovery action.
- No MCP token rotation or Tailscale identity change.
- No local application-image build.
- Development-fast deployment only after CI, Memory Governance and immutable images succeed on the exact final candidate head.
- Once a deployment request ID is accepted, never duplicate that deployment write.

## Validation lineage

- Original head `9136c42f...`: CI and immutable images passed; Memory Governance failed only for missing Session/Issue/Memory linkage.
- Session Issue #68, PR metadata and this Project Memory log resolved the governance gap.
- Hardened pre-PR66-refresh head `e028da31bd3d7c384ba26fcc6a9b4820c7065237`: PDP One CI #713 success, Memory Governance success, immutable Backend/MCP/Web image run #109 success.
- After PR66 merged, PR67 was refreshed onto main; all gates must be re-evaluated on the exact new combined code+memory head before deployment.

## Final runtime acceptance plan

1. Run CI, Memory Governance and immutable image builds on the exact final combined head.
2. PRE-DEPLOY Delta Sync against current main, open sessions/PRs and live PDP state.
3. Exact-commit deployment through the signed Deployment Agent; do not duplicate the request.
4. Independent deployment health check.
5. Read `get_procurement_analysis_run_status` and verify its new `statistics` payload: tender/inquiry/total counts, retry diagnostics and claim policy (`safe_claim_limit=50`, `global_active_claim_cap=400`, one active package per worker).
6. Verify PostgreSQL connectivity and contracts=10 / receivables=3 remain unchanged.
7. Verify the active analysis run ID is unchanged and was not cancelled/restarted.
8. PRE-MERGE Delta Sync; merge exact PR head only if no new overlap blocks it.
9. Record final deployment/health/statistics evidence and close Issue #68 without forcing an unnecessary second application deployment for documentation-only evidence.
