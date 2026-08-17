# PDP One — Automation Runtime Context

This is the compact **active-rule context** intended for PDP One scheduled analysis tasks. It is deliberately smaller than full project history.

## Version

- context schema: `pdp-automation-runtime-context-v2`
- capacity controller: `adaptive-packages-v2`
- generated for Session: `PDP-SESSION-20260817-ADAPTIVE-ANALYSIS-THROUGHPUT`

## Analysis invariants

- Source of active run truth: PDP One `get_procurement_analysis_run_status`.
- Source of active analysis Context: PDP One Context manifest/snapshot.
- Results are **AI Drafts** and require human review.
- AI Recommendation is not human Selection.
- Preserve `newest_first` and backend adaptive admission.
- Preserve run item ID, claim token, Notice ID, Content Hash and Context Hash on import.
- Semantic analysis is mandatory; keywords are context/search guidance, not deterministic scoring.
- Do not cancel/restart a healthy persistent run to change throughput.

## Throughput v2

Read `statistics.throughput` from the run-status response.

Important fields:

- `effective_backlog.raw_remaining`
- `effective_backlog.effective_remaining`
- `effective_backlog.redundant_reanalysis_ready_to_skip`
- `recent.completed_delta`
- `recent.lease_expired`
- `policy.desired_lanes`
- `policy.target_per_hour`
- `policy.package_size`
- `policy.max_packages_per_lane`
- `policy.backpressure`

### Package safety

- package size: backend-governed, currently **50** maximum;
- global in-flight cap: backend-governed, currently **400**;
- one active package per worker;
- after successful Import with no unresolved integrity errors, the same worker may immediately claim the next package;
- capacity comes from sequential package cycles, never from one giant claim.

### Adaptive targets

- effective >=50,000: desired 8 lanes / 20,000 per hour goal;
- 40,000–49,999: 8 lanes / 10,000 per hour goal;
- 20,000–39,999: 8 lanes / 7,500 per hour goal;
- 10,000–19,999: 6 lanes / 4,000 per hour goal;
- 5,000–9,999: 4 lanes / 2,000 per hour goal;
- 1,000–4,999: 2 lanes / 1,000 per hour goal;
- 1–999: lane 1 / 400 per hour maintenance goal.

Targets are **not guarantees**. The backend may reduce package cycles when recent lease-expiry evidence indicates caution/degraded health. Actual acceptance depends on measured imported/completed throughput and backlog trend.

## Lane behavior

- Lane 1 may start an incremental run only when no active run exists.
- Auxiliary lanes never create/cancel/restart runs.
- A lane exits when its lane number is greater than `policy.desired_lanes`.
- A lane loops up to `policy.max_packages_per_lane` only while execution remains healthy.
- Each loop is exactly: Claim up to 50 → semantic analysis of all items → one Import → verify successful clean checkpoint → next claim.
- A lane stops on `count=0`, Context sync failure, invalid/rejected import integrity, or inability to safely complete another package.
- During long runs, periodically re-read status/policy and obey reduced backpressure immediately.

## Semantic fast/deep behavior

Every record is semantically analyzed against the active PDP Context. Clear non-fit cases may use compact output. Detailed/deep-analysis candidates include recommended, urgent, ambiguous, needs-information and sufficiently high-score records. This is only a review-depth distinction; it is not keyword-only prefiltering and does not make final decisions.

## Effective backlog behavior

The legacy active full-pending run has `include_previously_analyzed=true`. Backend v2 may mark an open `explicit_reanalysis` item as `SKIPPED` only when the same Notice content under the same Context already has an exact valid draft/compact result and human review did not request revision. History is preserved; no Notice or analysis evidence is deleted.

## Model execution path

Current governed execution remains **ChatGPT Scheduled Tasks + PDP One MCP**. No separate server-side OpenAI API/model worker is assumed by this context.

## Forbidden side effects

Routine analysis Automations must not:

- approve/publish/select/submit an opportunity on behalf of the company;
- create a final contract, receivable or payment;
- delete Notice/Case/Opportunity/analysis history;
- change global Context/Prompt/keywords/company qualifications;
- rotate tokens;
- deploy application code;
- perform destructive Docker/volume operations.

## Failure behavior

If required Context/live run cannot be read, import integrity fails, or another claim is unresolved, stop at the latest clean imported checkpoint and report the concrete error. Do not silently fall back to a historical prompt, local heuristic queue or speculative bulk reservation.
