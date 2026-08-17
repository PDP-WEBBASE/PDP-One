# ADR-041 — Web UI No-Reload Interaction Policy

- Date: 2026-08-17
- Status: Active
- Decision ID: DEC-041
- Scope: PDP One web application
- Session: `PDP-SESSION-20260817-WEB-NO-RELOAD` / Issue #74

## Context

The user explicitly requires ordinary work in the PDP One web UI to remain continuous. Selecting a recommended tender was the observed example: after a successful mutation the procurement workspace performed a broad refresh, forcing the user to wait for session, list and dashboard reads before continuing. Similar hard reloads also existed in selected/submission/result enhancement flows.

The requirement is global rather than limited to the example: ordinary data entry, selection, stage changes, document/submission actions, results, settings and management mutations should not reload the whole page or unnecessarily rebuild the whole workspace.

## Decision

1. Ordinary authenticated UI mutations are **no-reload by default**.
2. A successful mutation updates only the affected local UI state and any directly affected counters/panels.
3. Optimistic UI is preferred when rollback is deterministic; otherwise the UI applies the confirmed server response locally.
4. Pending/error state should be local to the affected record or operation so unrelated user work can continue.
5. Cross-component reconciliation uses targeted background reads/events rather than page reload. Broad dataset reconciliation is allowed in the background only when the mutation genuinely has broad effects, such as completion of an extraction run.
6. Current tab, filters, search, scroll and unrelated loaded data should be preserved across ordinary mutations.
7. PostgreSQL/API remains authoritative. Optimistic changes must roll back on server failure and successful mutations remain subject to CSRF/session authorization.
8. AI recommendation and human selection remain distinct business facts. A selected recommended Notice leaves the actionable Recommended queue while recommendation history remains preserved according to DEC-016/DEC-017/DEC-023.

## Allowed exceptions

A full navigation/reload is permitted only when it is semantically required rather than used as mutation synchronization, including:

- crossing a real route/subsystem boundary;
- authentication/session recovery when the application cannot safely continue in-place;
- explicit emergency connectivity retry/recovery;
- loading a newly deployed client version when required.

These exceptions must not be used as a shortcut for normal CRUD/state synchronization.

## Implementation contract

The procurement workspace uses a shared `pdp-procurement-ui-sync` event contract for targeted Notice, Direct Opportunity, dashboard and management reconciliation. Row selection uses per-record pending state and optimistic rollback. Selected/submission/result enhancement flows update local state and notify sibling components instead of calling `window.location.reload()`.

Regression tests must prevent ordinary procurement mutation handlers from reintroducing hard reloads or global refresh behavior.

## Consequences

- The UI remains responsive while persistence occurs.
- Multiple independent row actions can proceed without blocking the entire workspace where server semantics allow it.
- More state reconciliation logic is explicit in the client, so tests must protect synchronization and rollback behavior.
- Emergency recovery/navigation behavior remains available without weakening the no-reload rule for normal work.
