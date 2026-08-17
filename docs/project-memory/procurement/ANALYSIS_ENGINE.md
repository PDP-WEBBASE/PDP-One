# PDP One — Procurement Analysis Engine

## Core invariant

The analysis engine produces **AI Drafts requiring human review**. It does not make the company's final tender/participation decision.

## Context

Analysis is tied to an identified Context snapshot:

- context snapshot ID
- context version
- context hash
- company profile/qualifications
- analysis prompt/policy
- keywords/domain guidance
- experience summary

A result import must preserve/validate the Context identity expected by the claim/run.

Bootstrap live Context:

- snapshot: `4612b6a6-ed18-4350-a636-f2a3e4ee26d9`
- version: 3
- hash: `67564111125cee3ee86a3f0709e18161fdc2298e1e832ef573999b01598beadf`

These are current only for the bootstrap timestamp; refresh live before Context-sensitive changes.

## Persistent run model

The long-running analysis process uses a persistent run with run items and checkpoint counters rather than a single one-shot page/batch.

Important concepts:

- Run ID / type / trigger / scope
- eligible run items
- pending/claimed/completed/retry/failed/poison states
- claim token
- lease expiration
- content hash
- Context hash
- import integrity
- checkpoint

Live bootstrap run:

`755ad573-0bdd-4437-9b3e-0f6f09a64b96`

It began on 2026-08-03 with stored configuration including `include_expired=true`, `include_previously_analyzed=true`, shard 250, deep batch 25 and stored workers 4.

Those creation-time settings must not be confused with newer queue/automation behavior.

## Frozen-run problem and PR58

Investigation in the current project chat found that the old persistent run could effectively behave as a frozen eligibility snapshot: notices arriving after run creation were not necessarily in the run backlog.

PR58 changed the active behavior:

- fresh eligible Notice records can be admitted to the already-running run;
- claim priority became `newest_first`;
- multi-lane claiming uses atomic DB claim/lease behavior;
- the run was not cancelled/restarted just to gain the new behavior.

A live proof after activation admitted **21,311** notices not present in the old frozen snapshot.

Historical snapshot immediately after that proof:

- total 43,944
- completed 6,670
- remaining 37,261
- pending 37,011
- claimed 250
- failed 0

Later bootstrap snapshot on 2026-08-17:

- total 51,632
- completed 12,326
- remaining 39,293
- pending 22,603
- claimed 5,968
- retry 10,722
- failed 0
- poison 13

These snapshots coexist; newer numbers do not erase older history.

## `newest_first`

PR58 states claim priority is based on newest activity, implemented with `last_seen_at` and then publication ordering. The exact queryset/order must be read from current code before modifying the policy.

Business intent:

> Fresh Tender/Inquiry notices must not wait behind a large historical backlog.

## Adaptive admission

The active run metadata exposes:

- `adaptive_admission=true`
- `priority_policy=newest_first`
- `draft_only=true`
- `human_review_required=true`

Admission expands the run as new eligible Notice records appear.

## Claim safety

Concurrent workers/lanes rely on atomic claims. A lane must:

1. read the active run;
2. claim bounded work with its own worker identity and lease;
3. analyze every claimed item against the active Context;
4. import results with the claim/content/context integrity fields;
5. only take the next claim after a successful import with no unresolved claim items.

Do not construct independent ad-hoc lists that bypass claim/lease integrity.

## AI output semantics

Historical/active compact results include concepts such as:

- recommended boolean
- score/priority/fit
- reasoning
- recommended action
- confidence
- matched criteria/experience
- needs information
- urgent
- deep-analysis candidate

The exact live schema belongs to current code/Context, not this document alone.

## Deep-analysis candidate policy in Hyper Turbo prompts

The currently created lane prompts historically mark deeper follow-up for cases such as:

- recommended
- urgent
- ambiguous / needs information
- sufficiently high score

This remains an AI Draft signal, not automatic selection.

## Re-analysis

The currently running full-pending run has `include_previously_analyzed=true`, which explains why its remaining total is not equivalent to “never analyzed” records only. A future run may use a different re-analysis policy; read live creation parameters and current decisions before interpreting backlog counts.

## Hyper Turbo desired capacity policy

Historical PR58 design:

| Remaining | Desired active lanes | Intended capacity concept |
|---|---:|---:|
| >=20,000 | 8 | very aggressive backlog clearance |
| 10,000–19,999 | 6 | aggressive |
| 5,000–9,999 | 4 | fast |
| 1,000–4,999 | 2 | moderate-fast |
| <1,000 | primary lane only / reduced claims | maintenance |

Only Lane 1 may create an incremental run if no active run exists. Auxiliary lanes must not create/cancel/restart runs.

This is **desired historical policy**, not proof of current live lane state.

## Current Automation Drift

At bootstrap, live ChatGPT Automation state showed:

- enabled: Lane 1, 2, 4, 6, 7, 8
- disabled: Lane 3, 5

Therefore actual live lane count was 6 even though remaining backlog exceeded 20k.

Do not auto-correct this drift in an unrelated session. Use a separately activated Automation change with current-state/throughput review.

## Throughput monitoring

When evaluating Turbo performance, measure actual results rather than theoretical claim capacity:

- imported/hour
- claimed/hour
- completed delta/hour
- fresh-notice latency
- retry rate
- poison count
- unresolved/import failures
- lease expirations
- backlog admission rate
- backlog net delta
- active lane state

## No destructive shortcuts

Do not improve throughput by:

- cancelling a healthy run and losing checkpoint state merely to recreate it;
- bypassing claim/import integrity;
- replacing semantic analysis with keyword-only scoring;
- automatically publishing recommendations;
- creating final business decisions.
