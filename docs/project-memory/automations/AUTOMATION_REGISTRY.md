# PDP One — ChatGPT Automation Registry

> Desired policy is versioned in GitHub. Actual enabled/schedule/prompt state must be read from ChatGPT Automations before mutation.

Last live verification for this change: **2026-08-17 ~22:20 +03:30**.

## Hyper Turbo analysis lanes — adaptive package-cycle v2

Shared purpose: consume the active procurement analysis run through atomic Claim → semantic analysis → Import cycles while preserving `newest_first`, adaptive admission, AI Draft output and human review.

### Core capacity contract

- Safe package size remains **50** records.
- Backend global active-claim cap remains **400** records.
- One worker may own only **one in-flight package** at a time.
- A worker may claim another package **immediately after its prior package imports successfully with no unresolved integrity errors**.
- A still-active package lease may be safely renewed by the same worker through `renew_procurement_analysis_claim`; expired claims are never resurrected and renewal never claims additional work.
- Throughput scales by repeated safe package cycles; it must **not** scale by reserving one giant 10k/20k claim.
- Backend `get_procurement_analysis_run_status.statistics.throughput.policy` is the desired capacity source for each live run.
- Targets are acceptance goals, not guarantees. Actual imported/hour, completed delta/hour, lease expiry, errors and backlog net delta decide success.

## Adaptive capacity targets

| Effective Remaining | Desired lanes | Target/hour | Package size | Max packages/lane/run at normal health |
|---:|---:|---:|---:|---:|
| >=50,000 | 8 | 20,000 | 50 | 50 |
| 40,000–49,999 | 8 | 10,000 | 50 | 25 |
| 20,000–39,999 | 8 | 7,500 | 50 | 19 |
| 10,000–19,999 | 6 | 4,000 | 50 | 14 |
| 5,000–9,999 | 4 | 2,000 | 50 | 10 |
| 1,000–4,999 | 2 | 1,000 | 50 | 10 |
| 1–999 | 1 | 400 | 50 | 8 |
| 0 | 0 | 0 | — | 0 |

The backend may reduce `max_packages_per_lane` when recent lease-expiry/error evidence indicates backpressure.

## Logical lanes

| Logical ID | Worker identity | Schedule | Lane number | Special rule |
|---|---|---|---:|---|
| PDP-AUTO-ANALYSIS-HYPER-LANE-01 | `pdp-hyper-lane-1` | hourly :00 | 1 | only lane allowed to create an incremental run when no active run exists |
| PDP-AUTO-ANALYSIS-HYPER-LANE-02 | `pdp-hyper-lane-2` | hourly :05 | 2 | auxiliary; never create/cancel/restart run |
| PDP-AUTO-ANALYSIS-HYPER-LANE-03 | `pdp-hyper-lane-3` | hourly :10 | 3 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-04 | `pdp-hyper-lane-4` | hourly :15 | 4 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-05 | `pdp-hyper-lane-5` | hourly :20 | 5 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-06 | `pdp-hyper-lane-6` | hourly :25 | 6 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-07 | `pdp-hyper-lane-7` | hourly :30 | 7 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-08 | `pdp-hyper-lane-8` | hourly :35 | 8 | auxiliary |

Live verification immediately before Session #80 implementation found **all eight lanes enabled**. This supersedes the bootstrap-day cached observation that lanes 3 and 5 were disabled; the historical drift remains preserved in older evidence.

## Lane execution contract

Every lane execution must:

1. Read `get_procurement_analysis_run_status`.
2. If no active run exists, only Lane 1 may call `start_incremental_analysis(include_expired=false)`; auxiliary lanes exit.
3. Read `statistics.throughput.policy`. Exit when `effective_remaining=0` or the lane number is greater than `desired_lanes`.
4. Loop no more than the current policy's `max_packages_per_lane`.
5. For each loop, call `claim_procurement_analysis_work` with that lane's worker ID, `limit=50`, `lease_seconds=3600`.
6. If count=0, stop. Never open a second package while one claim is unresolved.
7. Analyze every claimed record **semantically** against the active PDP Context. Keywords are context/search guidance only, never deterministic scoring.
8. Use a semantic fast pass for clear non-fit records while preserving structured reasoning. Recommended, urgent, ambiguous, needs-information or score>=60 records are detailed/deep-analysis candidates.
9. Preserve run item ID, claim token, Notice ID, Content Hash and Context Hash exactly.
10. If package processing is long or the lane is approaching Import after substantial work, call `renew_procurement_analysis_claim` for the same run/worker before Import. Renewal must return `renewed_items>0`; if it returns 0, do not import against a possibly expired claim—stop and report the checkpoint.
11. Import the complete package in one `import_procurement_analysis_results(..., dry_run=false)` call.
12. Take the next package only after the prior Import is successful and has no unresolved rejected/invalid-hash/invalid-context/error items.
13. Re-read status/policy periodically during long executions and obey lower backpressure/desired-lane values.
14. Finish with packages, claimed, imported/completed, errors, remaining and effective remaining.

If ChatGPT execution/runtime limits prevent the theoretical package count, stop only at a clean imported checkpoint; never reserve speculative future packages.

## Effective backlog rule

The historical active run was created with `include_previously_analyzed=true`. Backend v2 distinguishes raw Remaining from Effective Remaining. An open `explicit_reanalysis` row may be marked `SKIPPED` only when an exact current-content/current-Context valid draft or compact result already exists and human review did not request revision. The Notice, prior result and audit history are preserved. Full reconciliation scans are checkpointed/throttled rather than repeated on every package claim.

## Shared safety contract

- Results remain **AI Drafts requiring human review**.
- AI Recommended is not human Selected.
- Do not auto-select/publish/submit opportunities.
- Do not create final contract/receivable/payment/financial records.
- Do not delete business records or analysis history.
- Do not change Context/Prompt/keywords/qualifications/company history in routine lane execution.
- Do not cancel/restart the healthy persistent run to change capacity.
- Do not bypass claim/content/context integrity.
- Do not rotate tokens, deploy code or perform Docker/volume operations.

## Model execution architecture

This v2 change keeps the current **ChatGPT + PDP One MCP** analysis path. It does **not** introduce a separate OpenAI API key/provider or server-side model billing path. A future dedicated server-side model worker pool is a separate architecture/change decision and must not be assumed to exist.

## Automation change protocol

Before changing any live Task:

1. require active PDP One conversation mutation mode;
2. read this registry and `AUTOMATION_RUNTIME_CONTEXT.md`;
3. read actual live Automation(s);
4. read active analysis run/Context and backend throughput policy;
5. check active GitHub session/automation locks;
6. deploy and verify backend/MCP support before changing prompts that depend on it;
7. mutate only the governed Lane prompts/schedules needed;
8. verify live Task state after mutation;
9. record meaningful throughput/drift evidence, not every routine run payload.
