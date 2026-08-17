# Session — Web UI no-reload interaction hardening

- Session ID: `PDP-SESSION-20260817-WEB-NO-RELOAD`
- GitHub Issue: #74
- Pull Request: #75
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

## Concurrency correction

PR75 and PR67 had no direct changed-file overlap, but both exact deployments replace the full application image set. During PR75 PRE-MERGE synchronization, Session #68 exposed accepted PR67 deployment evidence that had not yet been visible when PR75 claimed its first deployment slot.

- PR67 accepted application candidate: `072a27a5af74d5170900c61f8162d6c4f6069a9f`.
- PR67 deployment: `analysis-retry-stats-072a27a5-20260817`, request `8b806cac-4689-4c2b-9abf-67664084494c`, accepted healthy with independent health in Session #68.
- PR75 first isolated deployment: exact `6dcc088706f6cb345b3df28cdfd5b56348d61b49`, deployment `web-no-reload-6dcc0887-20260817`, request `1aab73bf-7fbf-4d71-a8f2-7b2805314372`, succeeded/healthy. This deployment was not treated as final because it could replace the already accepted PR67 application image set.
- PR67 final head `37426e888b9c11f01e7ee8cb1f88a44c685f2790` differed from its accepted application candidate only in Project Memory documentation. Its CI, immutable images and Memory Governance passed.
- PR67 was merged as `58724bb427ed12dc2ffdb9f178f5085bd0c76988` without a second PR67 application deployment.
- PR75 was then refreshed onto that merged main. Combined application head: `7355376cc49750cd73a514a5d22b73f88ef7ab02`.
- Compare from merged PR67 main to the combined PR75 head showed only the nine intended no-reload UI/ADR/test files; PR67 backend changes remained in the combined tree.

The correction sequence preserves both accepted feature sets and avoids claiming that two sequential full-image deployments coexist automatically.

## Final exact-head gates

Combined exact application head: `7355376cc49750cd73a514a5d22b73f88ef7ab02`.

- PDP One CI: run `32052553295` — success.
- Immutable exact images: run `32052553283` — success for Backend, MCP and Web.
- Canonical Memory Governance validation job — success.
- The connector-readable wrapper failure was limited to GitHub Issue report publication; canonical validation itself succeeded and did not indicate a source/governance defect.
- Frontend lint and the complete npm test suite passed on the combined head, including `tests/procurement-no-reload-ui.test.mjs` and the updated Recommended/Selected workflow coverage.

## Final runtime acceptance

- Final accepted application exact commit: `7355376cc49750cd73a514a5d22b73f88ef7ab02`.
- Deployment ID: `combined-analysis-no-reload-7355376c-20260817`.
- Deployment request: `ffe43307-1025-474b-886b-443282d47ca2` — `succeeded`, deployment report `healthy`.
- Independent post-deployment health request: `01622cc7-31de-4b0f-bf60-7d5d28d240a2` — `succeeded / healthy`.
- Deployment Agent after acceptance: queue available, pending requests `0`, arbitrary shell disabled, disk reserve healthy.
- PDP One live system after acceptance: PostgreSQL connected, contracts `10`, receivables `3`; no destructive database operation or migration occurred.
- Active procurement analysis run remained `755ad573-0bdd-4437-9b3e-0f6f09a64b96`, running without cancel/restart.
- Live analysis statistics after the combined deployment exposed PR67 behavior: `priority_policy=newest_first`, `safe_claim_limit=50`, `global_active_claim_cap=400`, `one_active_package_per_worker=true`, with active claimed items bounded to `50` at verification time.

A first independent-health invocation crossed the MCP restart window and its client response was lost; it was not used as acceptance evidence. After the connection stabilized, the explicit request above returned a traceable `succeeded / healthy` result.

## Safety

- No database migration or destructive data change.
- No active analysis cancellation/restart.
- No MCP token/Tailscale change.
- No Docker/WSL/Rancher destructive operation.
- No local application image build; deployment used immutable GitHub Container Registry images.
- No automatic rollback.

## Merge rule

This final Project Memory update is documentation-only and occurs after accepted exact application deployment/health. It does not require a second application deployment. PRE-MERGE Delta Sync and exact-head governance/CI must still pass before merging PR75.
