# PDP One — Procurement Analysis Engine

## Core invariant

The analysis engine produces **AI Drafts requiring human review**. It does not make the company's final tender/participation decision.

## Context and integrity

Analysis is tied to an identified Context snapshot:

- context snapshot ID/version/hash;
- company profile and qualifications;
- active analysis prompt/policy;
- keyword/domain guidance;
- experience summary.

A result import must preserve/validate the run item ID, claim token, Notice ID, Notice Content Hash and Context Hash. These integrity checks remain mandatory at every throughput level.

## Persistent run model

The long-running process uses a persistent run with run items and checkpoints rather than a one-shot batch. Important item states include pending, claimed, completed, retry, poison, failed and skipped.

The long-lived run in the 2026-08-17 throughput session is:

`755ad573-0bdd-4437-9b3e-0f6f09a64b96`

It was originally created with `include_expired=true` and `include_previously_analyzed=true`. Those creation-time flags are historical properties of the run and must not be confused with current adaptive queue behavior.

## Fresh-admission and newest-first lineage

PR58 established:

- admission of newly eligible notices into the already-running persistent run;
- `newest_first` claim ordering;
- atomic DB claim/lease semantics;
- no cancel/restart merely to gain the new behavior.

Business invariant:

> Fresh Tender/Inquiry notices must not wait behind a large historical backlog.

`adaptive_admission=true` and `priority_policy=newest_first` remain required under throughput v2.

## PR67 backpressure lineage

PR67 responded to a large lease-expiry/retry storm by introducing:

- safe claim limit = **50**;
- global active-claim cap = **400**;
- one active package per worker;
- bounded compact claim payload;
- explicit retry diagnostics.

Those protections are **not removed** by throughput v2. Throughput does not come from one giant claim.

## Adaptive package-cycle throughput v2

Session `PDP-SESSION-20260817-ADAPTIVE-ANALYSIS-THROUGHPUT` changes the scaling model:

1. each worker claims at most one safe package (currently up to 50);
2. it semantically analyzes every item against the active Context;
3. it imports the complete package with integrity validation;
4. only after a successful clean Import may the same worker immediately claim the next package;
5. the number of sequential package cycles is governed by live effective backlog and health/backpressure.

This preserves PR67's bounded in-flight safety while removing the Automation-level one-package-per-hour bottleneck.

### Capacity targets

| Effective Remaining | Desired lanes | Target/hour | Normal max package cycles/lane |
|---:|---:|---:|---:|
| >=50,000 | 8 | 20,000 | 50 |
| 40,000–49,999 | 8 | 10,000 | 25 |
| 20,000–39,999 | 8 | 7,500 | 19 |
| 10,000–19,999 | 6 | 4,000 | 14 |
| 5,000–9,999 | 4 | 2,000 | 10 |
| 1,000–4,999 | 2 | 1,000 | 10 |
| 1–999 | 1 | 400 | 8 |

These values are **goals**, not promised throughput. Backend may reduce package cycles under recent lease-expiry/error pressure. Runtime acceptance is based on actual imported/completed rate and backlog trend.

## Raw Remaining versus Effective Remaining

Because the active historical run has `include_previously_analyzed=true`, raw `remaining` can include `explicit_reanalysis` rows even when an exact analysis already exists.

Throughput v2 therefore publishes an **Effective Backlog**. An open explicit-reanalysis item is safe to reconcile as `SKIPPED` only when:

- it is not an active claim;
- an exact result exists for the same Notice content and same active Context;
- the exact result is either a valid NoticeAnalysisDraft or completed compact result;
- human review did **not** mark that result `needs_revision`.

Reconciliation:

- never deletes the Notice;
- never deletes the prior analysis;
- marks only the redundant run item `SKIPPED`;
- records `analysis_reason=already_valid_current_analysis`;
- preserves audit/history.

Thus `raw_remaining` and `effective_remaining` must both be visible when diagnosing backlog.

## Lease-expiry health and backpressure

When stale active claims expire, the backend returns them to `RETRY` and records lease-expiry events. The throughput controller observes recent completed imports versus recent lease expiries.

- normal health: use configured package-cycle target;
- caution: reduce cycles;
- degraded: reduce more aggressively;
- package size and global in-flight safety remain bounded.

The intent is to favor **completed imports over speculative reservations**.

## Semantic fast pass and detailed/deep candidates

Throughput must not be achieved by replacing semantic analysis with deterministic keyword scoring.

Every claimed notice is semantically assessed against the active PDP Context. Output depth may differ:

- obvious non-fit records may return compact structured semantic results;
- recommended, urgent, ambiguous, needs-information or sufficiently high-score records are detailed/deep-analysis candidates.

The existing Import layer stores compact non-material results on the run item and creates a full `NoticeAnalysisDraft` for material/detailed review cases. Both remain AI-generated evidence and do not constitute a final participation decision.

## Multi-lane Automation behavior

- Lane 1 may start an incremental run only when no active run exists.
- Auxiliary lanes never create/cancel/restart runs.
- Backend policy exposes desired lane count and max package cycles.
- Every lane keeps its stable worker identity.
- A lane takes the next package only after prior Import completes cleanly.
- If execution limits are reached, the lane stops at a clean imported checkpoint rather than opening speculative claims.

Current desired Automation contract lives in `docs/project-memory/automations/AUTOMATION_REGISTRY.md` and compact task rules live in `AUTOMATION_RUNTIME_CONTEXT.md`.

## Model execution architecture

The current governed analysis path remains **ChatGPT Scheduled Tasks + PDP One MCP**. Session #80 does not introduce a separate OpenAI API credential, server-side model provider or hidden model-billing path.

A future dedicated server-side model-worker pool would be a separate architecture decision requiring explicit provider, cost, security, rate-limit and deployment design. Do not claim that it exists under throughput v2.

## Throughput monitoring and acceptance

Measure actual behavior, not theoretical capacity:

- imported/hour;
- completed delta/hour;
- packages completed per lane;
- lease expirations/hour and ratio;
- rejected/invalid-hash/invalid-context/import errors;
- effective backlog and raw backlog;
- fresh-notice latency;
- admission rate and backlog net delta;
- poison/failed counts;
- active desired/live lane state.

A 10k/h or 20k/h target is accepted only after measured evidence supports it. Otherwise report the actual sustainable throughput and remaining bottleneck.

## Historical snapshots

Earlier snapshots remain valid for their timestamps and must not be overwritten as current truth. Examples preserved in project history include:

- after PR58 admission proof: total 43,944 / completed 6,670 / remaining 37,261;
- bootstrap 2026-08-17: total 51,632 / completed 12,326 / remaining 39,293 / retry 10,722;
- Session #80 start live state: total 54,397 / completed 12,980 / remaining 41,404 / retry 18,321 / `claim_lease_expired` 18,237.

## No destructive shortcuts

Do not improve throughput by:

- cancelling/restarting the healthy active run merely for capacity;
- enlarging one claim to thousands of records;
- bypassing atomic claim/import integrity;
- replacing semantic analysis with keyword-only scoring;
- deleting valid historical results to reduce counts;
- automatically publishing or selecting recommendations;
- creating final contract/receivable/payment decisions.
