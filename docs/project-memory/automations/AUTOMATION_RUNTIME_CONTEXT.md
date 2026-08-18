# PDP One — Automation Runtime Context

This is the compact **active-rule context** intended for PDP One scheduled tasks. It is deliberately smaller than the full project history.

## Version

- context schema: `pdp-automation-runtime-context-v1`
- generated during canonical-memory bootstrap: 2026-08-17
- live Automation drift exists; see Automation Registry

## Analysis rules

- Source of active run truth: PDP One `get_procurement_analysis_run_status`.
- Source of active analysis Context: PDP One Context manifest/snapshot.
- Results are **AI Draft**.
- `requires_human_review=true`.
- AI Recommendation is not human Selection.
- Backend claim policy: `newest_first` when reported by live run.
- Backend fresh-record admission: use active adaptive admission; do not create a separate local backlog order.
- Preserve claim/content/context identity on import.
- Do not use rule-based keyword scoring as a replacement for semantic ChatGPT analysis.

## Lane safety

- Lane 1 may start an incremental run only when no active run exists.
- Auxiliary lanes must not create/cancel/restart runs.
- Do not cancel a healthy persistent run merely because backlog/config changed.
- Claim only through the governed atomic claim API.
- Do not take a new claim until prior claim import is successful and unresolved items are handled.

## Historical desired thresholds

- >=20,000 remaining: desired lanes 1–8
- 10,000–19,999: desired lanes 1–6
- 5,000–9,999: desired lanes 1–4
- 1,000–4,999: desired lanes 1–2
- <1,000: lane 1, reduced claims

**Actual live task enablement must be read from ChatGPT Automations.** Do not infer it from this desired table.

## Current drift marker at generation

At bootstrap, lanes 3 and 5 were disabled while remaining backlog exceeded 20,000.

`automation_drift_status: OPEN`

A routine scheduled task should not self-enable another Task. Drift correction is a separate governed project change.

## Forbidden side effects

Routine analysis Automations must not:

- approve/publish/select an opportunity on behalf of the company;
- create a final contract, receivable or payment;
- delete Notice/Case/Opportunity business history;
- change global Context/Prompt/keyword/company qualifications;
- rotate tokens;
- run destructive Docker/volume operations;
- deploy application code.

## Failure behavior

If required Context/live run cannot be read or import integrity fails, record/return `context_sync_failed` or the concrete error and avoid a risky write. Do not silently fall back to an obsolete historical prompt or local heuristic queue.
