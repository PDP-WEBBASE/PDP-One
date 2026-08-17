# ADR-042 — Adaptive package-cycle procurement analysis throughput

- Status: Accepted design / runtime acceptance required
- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-ADAPTIVE-ANALYSIS-THROUGHPUT`
- Issue: #80
- PR: #83

## Context

The live active procurement run had 54,397 total items, 12,980 completed and 41,404 remaining. Eight hourly Hyper Turbo ChatGPT lanes were enabled but each live prompt intentionally performed only one 50-item claim, creating a theoretical ceiling near 400 results/hour. Meanwhile retry stood at 18,321, including 18,237 historical/current `claim_lease_expired` items.

PR67 had intentionally introduced a safe 50-item claim limit, global active-claim cap of 400 and one active package per worker after a previous speculative-claim/lease-expiry storm. Those protections are valuable and must not be reversed merely to raise throughput.

The active historical run was also created with `include_previously_analyzed=true`, so raw Remaining can include explicit reanalysis even when an exact same-content/same-Context result already exists.

## Decision

### 1. Preserve bounded in-flight safety

Keep:

- safe package size <=50;
- global active-claim cap 400;
- one active package per worker;
- atomic claim token + Notice Content Hash + Context Hash validation;
- `newest_first` and adaptive fresh-notice admission.

Do not create giant 10k/20k claims.

### 2. Scale by sequential package cycles

After a worker imports its current package successfully with no unresolved integrity errors, it may immediately claim the next safe package in the same Automation execution. Throughput is therefore controlled by package cycles per lane, not by increasing claim size.

### 3. Use Effective Backlog for catch-up capacity

Expose both raw Remaining and Effective Remaining. An open `explicit_reanalysis` item may be marked `SKIPPED` only when an exact valid same-content/same-Context draft or compact result already exists and human review did not request revision. Preserve the Notice, prior result and audit history.

### 4. Adaptive capacity goals

- effective >=50k: 20k/hour goal, 8 lanes;
- >=40k: 10k/hour, 8 lanes;
- >=20k: 7.5k/hour, 8 lanes;
- >=10k: 4k/hour, 6 lanes;
- >=5k: 2k/hour, 4 lanes;
- >=1k: 1k/hour, 2 lanes;
- <1k: 400/hour maintenance, lane 1.

Backend converts these goals to package cycles per lane and reduces cycles under measured lease-expiry/error backpressure. Goals are never presented as guaranteed throughput without runtime evidence.

### 5. Preserve semantic quality with variable output depth

Every claimed record receives semantic analysis against active PDP Context. Obvious non-fit items can use compact structured results. Recommended, urgent, ambiguous, needs-information and high-score records remain detailed/deep-analysis candidates. Deterministic keyword-only scoring is prohibited.

### 6. Keep current model execution architecture

This decision retains ChatGPT Scheduled Tasks + PDP One MCP. It does not add a separate OpenAI API credential/provider or server-side model worker pool. A future dedicated provider-backed worker pool requires a separate decision covering cost, credentials, rate limits, privacy/security, failure isolation and deployment.

## Consequences

Positive:

- removes the Automation one-package/hour bottleneck without undoing PR67 safety;
- can consume multiple safe packages per lane per hour;
- avoids spending capacity on exact already-valid reanalysis;
- provides explicit health/backpressure and measurable acceptance metrics;
- preserves newest-first behavior for incoming opportunities.

Risks/limits:

- ChatGPT scheduled execution limits may prevent theoretical 10k/20k targets even when backend permits enough cycles;
- if lease expiry rises, controller must reduce cycles rather than continue speculative claiming;
- sustained 10k–20k/h may ultimately require the separately governed provider-backed worker architecture.

## Acceptance criteria

This ADR becomes runtime-accepted only after:

- exact-head CI/Memory/image gates pass;
- exact commit is deployed and healthy;
- Effective Backlog is readable live;
- no unsafe skip of `needs_revision` work is observed;
- Hyper Turbo live prompts are updated to consume backend policy;
- measured imported/completed throughput and lease/error behavior are recorded honestly.
