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

## Exact-head gates before deployment

Accepted application exact commit: `7973fcb4716f26529c2b24817bd177fd32d48387`.

- PDP One CI run `32056627002` / #733 — **success**.
  - Windows PowerShell 5.1 compatibility — success.
  - secret/destructive-volume scan — success.
  - frontend install/lint/tests — success.
  - Python syntax/migration verification — success.
  - signed deployment queue tests — success.
  - backend tests, including the new automation-settings API coverage — success.
- Immutable exact images run `32056626975` / #128 — **success** for Backend, MCP and Web.
- Memory Governance runs `32056626904` / #62 and `32056643176` / #63 — **success** after the required PR Session/Issue/Memory linkage was corrected.
- PRE-DEPLOY `main` remained `cc5852ac5fa797c98624976881a74764ae13056c`; the only open PDP Session Issue was #77; PR78 remained at exact head `7973fcb...` and mergeable.

## Runtime acceptance

Development-fast exact deployment:

- exact application commit: `7973fcb4716f26529c2b24817bd177fd32d48387`
- deployment ID: `schedule-editor-7973fcb4-20260817`
- deployment request: `e68939d4-bacc-48e4-913d-078749a06812`
- terminal result: **succeeded**
- deployment report health: **healthy**
- backup: skipped as expected under `development_fast`

The MCP connection briefly dropped while the service restarted. No duplicate deployment was created; the same exact request was polled after reconnection and returned the terminal success above.

Independent post-deployment short health:

- health request: `e6312dab-86c0-4c46-97eb-c4ef2f0cc888`
- result: **succeeded / healthy**
- ChatGPT tool check: `reported-through-connected-app`

Post-acceptance operational checks:

- Deployment Agent: queue available, pending requests `0`, completed responses `289`, arbitrary shell disabled, disk reserve healthy.
- PDP One: PostgreSQL connected; contracts `10`; receivables `3`.
- No destructive database operation or migration occurred.
- Crucially, the live automation schedule remained exactly unchanged after deployment: existing record `864f59ed-26c3-4749-91c8-3faff3ed5c95`, enabled `true`, cadence `hourly`, interval `60` minutes, timezone `Asia/Tehran`, `daily_time=null`. The deployment therefore did not silently apply the 11:00 fallback or alter the user's current schedule.

## Safety

- No destructive database or Docker volume operation.
- No database migration.
- No ChatGPT Automation mutation.
- No local application-image build; deployment used immutable exact images from CI.
- No token or credential rotation.
- No automatic rollback.
- DEC-041 no-reload behavior remains in force.

## Merge rule

This final Project Memory update is documentation-only and occurs after accepted exact application deployment/health. It does not require a second application deployment. The final PR head must still pass exact-head CI/Memory Governance as applicable and a PRE-MERGE Delta Sync before PR78 is merged and Issue #77 is closed.
