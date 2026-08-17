# PDP One — ChatGPT Automation Registry

> Desired policy is versioned in GitHub. Actual enabled/schedule/prompt state must be read from ChatGPT Automations before mutation.

Bootstrap verification: 2026-08-17.

## Hyper Turbo analysis lanes

Shared purpose: consume the active procurement analysis run through atomic claim/import workflow, with newest-first/adaptive-admission backend behavior, AI Draft outputs and human review.

| Logical ID | Worker identity | Live state at bootstrap | Schedule | Run condition in live prompt | Max claims/run | Claim request | Notes |
|---|---|---|---|---|---:|---|---|
| PDP-AUTO-ANALYSIS-HYPER-LANE-01 | `pdp-hyper-lane-1` | **enabled** | hourly | active run; if none may start incremental; <1000 uses reduced max claims | 4 normally / 2 under 1000 | limit 500, lease 3600 | only lane allowed to create a new incremental run |
| PDP-AUTO-ANALYSIS-HYPER-LANE-02 | `pdp-hyper-lane-2` | **enabled** | hourly | remaining >=1000 | 4 | limit 500, lease 3600 | never create/cancel/restart run |
| PDP-AUTO-ANALYSIS-HYPER-LANE-03 | `pdp-hyper-lane-3` | **DISABLED** | hourly config | remaining >=5000 | 4 | limit 500, lease 3600 | desired historical policy expected it active above threshold; drift |
| PDP-AUTO-ANALYSIS-HYPER-LANE-04 | `pdp-hyper-lane-4` | **enabled** | hourly | remaining >=5000 | 4 | limit 500, lease 3600 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-05 | `pdp-hyper-lane-5` | **DISABLED** | hourly config | remaining >=10000 | 4 | limit 500, lease 3600 | desired historical policy expected it active above threshold; drift |
| PDP-AUTO-ANALYSIS-HYPER-LANE-06 | `pdp-hyper-lane-6` | **enabled** | hourly | remaining >=10000 | 4 | limit 500, lease 3600 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-07 | `pdp-hyper-lane-7` | **enabled** | hourly | remaining >=20000 | 4 | limit 500, lease 3600 | auxiliary |
| PDP-AUTO-ANALYSIS-HYPER-LANE-08 | `pdp-hyper-lane-8` | **enabled** | hourly | remaining >=20000 | 4 | limit 500, lease 3600 | auxiliary |

### Current drift

Historical PR58 desired capacity policy described 8 lanes when remaining >=20,000. Live bootstrap remaining was 39,293 but lanes 3 and 5 were disabled.

`AUTOMATION_DRIFT: OPEN`

This bootstrap **does not** enable/disable live tasks. Schedule mutation requires a separate activated `PDPONE START` session that refreshes run state, live task state, active sessions and relevant performance evidence.

## Shared safety contract for Hyper Turbo

- Read active run before claiming.
- Backend provides fresh adaptive admission and `newest_first`; do not recreate a local keyword queue.
- Preserve `run_id`, claim token, content hash and Context hash integrity.
- Analyze all items in the claim semantically using current PDP Context.
- Import each claim as AI Draft; require human review.
- Only claim again after successful import/no unresolved items.
- Do not auto-select/publish opportunities.
- Do not create contract/receivable/payment/financial records.
- Do not delete records.
- Do not modify Context/Prompt/keywords/qualifications/company history inside routine lane execution.
- Auxiliary lanes do not create/cancel/restart runs.

## Historical desired adaptive capacity policy

| Remaining backlog | Desired lane set | Intent |
|---|---|---|
| >=20,000 | 1–8 | Hyper Turbo |
| 10,000–19,999 | 1–6 | aggressive |
| 5,000–9,999 | 1–4 | fast |
| 1,000–4,999 | 1–2 | moderate-fast |
| <1,000 | lane 1 reduced | maintenance |

This table is a desired historical policy. Actual task enablement must be verified live.

## Older ChatGPT tasks preserved as historical state

The Automation service also contains disabled older/test tasks, including:

- one-time `تحلیل کامل PDP One`
- PDP One 24h/48h checks
- older GitHub scheduled-write tests
- old tender-analysis task
- Google Drive capability tests
- old Pars-Namad daily task

These are historical Automation evidence. Their disabled presence must not be confused with the active Hyper Turbo architecture or deleted merely for tidiness.

## Automation change protocol

Before changing any live Task:

1. require `PDPONE START`;
2. read this registry and `AUTOMATION_RUNTIME_CONTEXT.md`;
3. read actual live Automation(s);
4. read active analysis run/Context if relevant;
5. check active GitHub session locks;
6. compare desired vs actual state and identify drift;
7. make only the requested change;
8. verify live Task after mutation;
9. update registry/spec/runtime context and Session Issue immediately.

Do not use a historical task prompt as the only policy source when GitHub has a newer active spec.
