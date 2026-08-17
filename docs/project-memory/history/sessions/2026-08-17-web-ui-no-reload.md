# Session — Web UI no-reload interaction hardening

- Session ID: `PDP-SESSION-20260817-WEB-NO-RELOAD`
- GitHub Issue: #74
- Branch: `feat/web-ui-no-reload-20260817`
- Starting main: `66bae829ff2e93d92c2c494dec187def8cdf0c6e`
- User authorization: explicit `تأیید، اجرا کن` in an ACTIVE PDPONE Conversation

## User requirement

The observed tender selection reload was an example of a global UX requirement: ordinary PDP One web activities must not reload the whole page or interrupt ongoing work. Data entry, selection, stage transitions, submission/document actions, results, settings and management mutations should update the relevant UI in place while persistence/reconciliation happens through the API.

## Findings

- `ProcurementWorkspaceV13` used a global `setRefresh()` after several ordinary mutations. That re-read session, notices/direct opportunities and dashboard and triggered wider background collection loading.
- `ProcurementWorkspaceEnhancements` used `window.location.reload()` after selected-case removal, Direct Opportunity stage changes and document/submission completion.
- `ProcurementSubmissionResultsEnhancements` used `window.location.reload()` after AI recommendation dismissal, zero-file submission and result registration.
- The main contracts/finance shell already performs ordinary creation with local React state and does not hard reload.
- Route navigation to `/procurement` is a real subsystem navigation and is not mutation synchronization.
- The explicit connectivity-failure retry in `ProcurementWorkspaceV14` remains an allowed emergency recovery exception.

## Implementation

- Added `app/procurement/procurementUiSync.ts` as the shared cross-component reconciliation event contract.
- Notice selection now uses per-record pending state, optimistic move to Selected, server confirmation and rollback on failure.
- The actionable Recommended view excludes records that already have a human Case while preserving recommendation history.
- Connector toggles, extraction request creation and Direct Opportunity creation update local state rather than globally refreshing the workspace.
- Extraction completion performs background broad reconciliation only after the run becomes terminal.
- Selected-case removal, Direct Opportunity stage changes, document/submission completion, recommendation dismissal, zero-file submission and result registration no longer call `window.location.reload()`.
- Sibling components reconcile affected Notice/Direct Opportunity/dashboard/management state through targeted events and reads.
- Added regression test `tests/procurement-no-reload-ui.test.mjs`.
- Added ADR-041 / DEC-041 policy definition.

## Concurrency and deployment

- PR66 / Session #61 owns MCP stability/infrastructure and currently has deployment sequencing priority.
- PR67 / Session #68 owns analysis retry/statistics.
- The no-reload branch has no known direct changed-file overlap with those active PRs at implementation time.
- Exact-image deployment must still be sequenced through PRE-DEPLOY Delta Sync; no competing deployment request is permitted.

## Safety

- No database migration or destructive data change.
- No active analysis cancellation/restart.
- No MCP token/Tailscale change.
- No Docker/WSL/Rancher destructive operation.
- No local application image build.

## Verification

Source audit and regression tests were added before PR creation. CI / immutable image / deployment / runtime acceptance evidence is appended through the Session Issue and PR as the work progresses.
