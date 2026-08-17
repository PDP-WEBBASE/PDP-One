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

## Change scope

- Add per-worker backpressure: a worker with an open, unexpired claim does not receive a second package.
- Add a global open-claim ceiling for the active run.
- Cap direct ChatGPT packages at 50 records with a conservative payload ceiling.
- Preserve atomic claims, adaptive admission and `newest_first` ordering.
- Add exact analysis statistics broken down by `tender`, `inquiry` and `total` for notice population, run population/status, attempted-by-ChatGPT, completed/remaining and AI draft/recommendation visibility.
- Add retry diagnostics including lease-expiry and attempts distribution.
- Expose the statistics through a read-only MCP tool.

## Operational mitigation already applied

Before application deployment, the eight scheduled Hyper Turbo lanes were reduced to at most one claim of 50 records per hourly execution and staggered by five minutes. This mitigation is intentionally conservative until the backend backpressure gate is live and measured.

## Concurrency coordination

Open Session #61 / PR66 owns a broad `services/pdp_mcp/**` soft lock for MCP transport stability. Exact changed-file comparison found no file-level overlap: PR66 changes MCP transport/health files while PR67 changes only `services/pdp_mcp/procurement_analysis_tools.py` inside that subtree. PR67 will not modify PR66 files or transport behavior. PRE-DEPLOY and PRE-MERGE context sync are mandatory.

## Safety constraints

- Do not cancel or restart the active procurement analysis run.
- Do not delete healthy drafts or completed results.
- Do not change PostgreSQL business data except ordinary analysis claim/import state transitions performed by the existing workflow.
- No destructive Docker volume, WSL, Rancher or filesystem recovery action.
- No MCP token rotation or Tailscale identity change.
- No local application-image build.
- Development-fast deployment only after CI, Memory Governance and immutable images succeed on the exact candidate head.
- Once a deployment request ID is accepted, never duplicate that deployment write.

## Validation status

Initial code head `9136c42f...` passed PDP One CI and immutable Backend/MCP/Web image builds. Memory Governance failed only because the PR body lacked PDP Session / Active-work Issue declarations and the branch lacked a Project Memory update. Issue #68, PR metadata and this session log close that governance gap; all gates must be re-evaluated on the new exact head.

## Runtime acceptance plan

1. Re-run CI, Memory Governance and immutable image builds on the exact final code+memory head.
2. PRE-DEPLOY Context Sync against open sessions/PRs and live PDP state.
3. Exact-commit deployment through the signed Deployment Agent.
4. Independent deployment health check.
5. Read the new split statistics endpoint/tool and verify tender/inquiry/total counts and retry diagnostics.
6. Verify PostgreSQL connectivity and contracts/receivables unchanged.
7. Observe claimed/retry behavior; no manual cancellation of existing retry items.
8. PRE-MERGE Context Sync; merge exact PR head only if no new overlap blocks it.
9. Record deployment/health/statistics evidence in PR/Issue and close the session when complete.
