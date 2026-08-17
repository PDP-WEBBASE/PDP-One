# Session — Procurement extraction schedule editor repair

- Session ID: `PDP-SESSION-20260817-EXTRACTION-SCHEDULE-EDITOR`
- GitHub Issue: #77
- Pull Request: #78
- Branch: `fix/procurement-extraction-schedule-editor-20260817`
- Starting main: `cc5852ac5fa797c98624976881a74764ae13056c`
- Conversation activation: ACTIVE via `PDPONE START`

## User requirement

The Procurement > Extraction & Sources > incremental extraction schedule editor must allow the system owner to change and persist enabled/disabled state, daily/hourly cadence, daily time or hourly interval. The visible fallback/default when no server settings are available should be daily at 11:00 in `Asia/Tehran`. Saving settings must not itself start an extraction; `استخراج اکنون` remains a separate explicit action.

## Live finding before implementation

The warning shown by the browser did not prove that the database row was absent. Live PDP One runtime verification showed an existing `ProcurementAutomationSettings` record with key `default`, enabled `true`, cadence `hourly`, interval `60` minutes and timezone `Asia/Tehran`.

Therefore the existing live schedule must not be silently replaced during deployment. The 11:00 value is a safe UI/repair fallback only; changing the actual live schedule remains an explicit administrator action through the editor.

## Root cause

- `ProcurementWorkspaceV13` loaded sources, extraction history and automation settings in one `Promise.all`; a failure of any one management request could prevent all three panels from being populated.
- `saveAutomation()` aborted whenever browser state `automation` was null, even if the database record actually existed.
- Save depended on the UUID of a settings record first being loaded into browser state.
- The local schedule fallback was daily `07:30`, not the required `11:00`.

## Implementation

### Backend

- Added `GET/PATCH /api/v1/procurement/automation-settings/default/`.
- GET is read-only and does not create a missing row.
- Admin PATCH can safely repair a genuinely missing `key=default` record with an **inactive** daily 11:00 `Asia/Tehran` baseline and then applies the administrator's explicit validated payload.
- Existing serializer validation remains authoritative, including the 60-minute minimum interval and required time for an enabled daily schedule.
- Updates remain audit logged.

### Frontend

- Schedule save no longer depends on a UUID already loaded into local React state.
- The fallback form is inactive + daily + 11:00 + 1 hour.
- Sources, extraction history and automation settings load independently through `Promise.allSettled`; a failure in one management request does not prevent successful sibling requests from populating their panels.
- After a successful save, the UI uses the actual server response and shows the stored enabled state and next extraction time when available.
- Saving only persists schedule settings. It does **not** invoke an extraction run; the separate `استخراج اکنون` button remains explicit.
- `ProcurementWorkspaceV14.tsx` is intentionally left byte-identical to canonical `main`; this repair does not broaden the global fetch-guard behavior.

## Tests added

`backend/procurement/tests/test_automation_settings_api.py` covers:

- missing default GET remains read-only;
- admin PATCH creates a missing default and persists daily 11:00;
- a subsequent PATCH updates the same singleton record to hourly mode;
- non-admin mutation is forbidden;
- enabled daily schedule without a time is rejected.

## Concurrency

Two same-branch commits appeared while this Conversation was implementing the work:

1. `53edc15105c1ddc8beeab62543125f19aaa9dfc8` temporarily broadened `ProcurementWorkspaceV14.tsx` fetch-guard behavior into the schedule scope.
2. `9ad64051450f9772fa190dae85ecef5d1eb3e8f1` explicitly reverted that broadening with message `chore: keep schedule fix scoped to V13 and API`.

No separate open `[PDP SESSION]` Issue was found for that work. The final branch was reconciled by restoring `ProcurementWorkspaceV14.tsx` to the exact blob on `main` (`3a35373000b8379767ca04e6fe69ca4d57d5b34e`). The accepted functional scope is therefore V13 + automation-settings API/tests only.

Concurrency Check: `OVERLAP → RECONCILED / SCOPE RESTORED`.

## Safety

- No destructive database or Docker volume operation.
- No database migration is required.
- Deployment itself must not alter the existing live schedule.
- No ChatGPT Automation mutation is part of this work.
- No local application-image build.
- No token or credential rotation.
- DEC-041 no-reload behavior remains in force.

## Acceptance status

Functional implementation head before memory/governance-only follow-up commits: `6a1646d6f00f913056171760c90f4de04fb88599`.

- Memory Governance initially blocked PR78 because the PR body lacked the required machine-readable Session/Issue/Memory linkage and the code PR had no Project Memory file. This session log and corrected PR metadata resolve that governance defect rather than bypassing the gate.
- Final exact-head CI / immutable image / Memory Governance: pending after the governance/scoping follow-up commits.
- Exact runtime deployment/health: pending.
- Merge: pending.

This file must be updated with exact final CI, deployment request/ID, health evidence, final application commit and merge evidence before Session #77 is closed.
