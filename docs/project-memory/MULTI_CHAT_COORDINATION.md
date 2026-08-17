# PDP One — Multi-Chat Coordination

PDP One may be changed by more than one ChatGPT conversation at the same time. GitHub is the shared coordination plane.

## Session lifecycle

An operational chat begins only after the user activates `PDPONE START`.

After Context Sync and before its first project write, create a GitHub Session Issue with:

- Session ID
- start time
- user request
- current `main`
- scope/modules
- expected files
- database entities
- runtime resources
- automations
- related decisions
- related active sessions
- branch / PR
- phase
- last heartbeat
- blockers/conflicts
- next action

Issue #59 is the first bootstrap example of this protocol.

## Soft lock

Declare:

```yaml
lock_scope:
  modules: []
  files: []
  database: []
  runtime: []
  automations: []
```

It is a governance lock rather than an OS/Git lock. Other sessions must inspect it before writing.

## Mandatory context checkpoints

### START
Before designing/implementing:
- read canonical memory
- read `main`
- read active session issues
- read open PRs
- refresh relevant runtime/automation state

### PRE-WRITE
Immediately before significant code/config/schema/automation change:
- refresh `main`
- refresh active work
- ensure scope remains clear

### PRE-DEPLOY
Before any deploy:
- refresh `main`
- compare branch base/head
- inspect concurrent deployment work
- verify exact commit/images/agent state
- stop on unresolved deployment overlap

### PRE-MERGE
Immediately before merge:
- refresh `main`
- inspect all active sessions and PRs
- verify deployment/health evidence when deployment was required
- reconcile changes made by other sessions since START

## Concurrency result

Record one:

- `Concurrency Check: CLEAR`
- `Concurrency Check: OVERLAP`

An overlap is not automatically fatal, but it must be resolved before conflicting work proceeds.

## Conflict resolution modes

- **Split** — separate non-overlapping modules/files/resources.
- **Sequence** — one session finishes before the other proceeds.
- **Integrate** — the second session intentionally builds on the first branch/PR.
- **Rebase/Refresh** — update a stale branch after relevant changes land.
- **Explicit conflict acceptance** — user knowingly authorizes managed overlap after the risks are recorded.

## High-risk overlap classes

Always treat these as potential conflicts:

- same source file/module
- same database model or migration
- same deployment target/phase
- same ChatGPT Automation
- same runtime configuration/resource
- same connector/parser
- same global analysis Context

## Deployment lock

A Session Issue in an active deployment phase acts as a soft deployment lock. Another chat must not start an independent overlapping deployment until the active request reaches a terminal state or the overlap is explicitly coordinated.

Once an exact deployment Request ID exists, follow that request; do not create a duplicate deploy write merely because MCP temporarily disconnects during service restart.

## Automation lock

A session changing an Automation declares its logical IDs in `lock_scope.automations`. Another session must read the lock and current live Automation before changing the same Task.

## Migration lock

Sessions that touch database migrations/models declare them. Concurrent migration creation on overlapping model history must be sequenced or explicitly reconciled.

## Heartbeats

Update the Session Issue after meaningful milestones, especially:

- user decision
- scope change
- branch created
- commit/head changed
- PR created
- CI failure/success
- root cause discovery
- preview
- deploy request accepted
- deploy terminal result
- independent health result
- runtime data observation
- automation mutation/drift discovery
- merge
- blocker/next action

This allows a second chat to see an in-progress change before the first chat finishes.

## `main` changes during a session

If `main` changed after START:

1. identify the new commits/PR/session;
2. read the relevant change;
3. compare it with your scope;
4. reconcile/rebase as required;
5. rerun relevant tests;
6. repeat PRE-DEPLOY/PRE-MERGE checks.

Do not deploy or merge from stale context.

## Interrupted chats

If a chat ends unexpectedly, leave its Issue open with the latest known:

- commit/branch
- CI state
- deployment Request ID if any
- pending operation
- blocker
- next action

A new activated chat may resume it only after new Context Sync and conflict check.

## Closing a session

A successful session must produce/update a permanent Session Log in `docs/project-memory/history/sessions/`, sync relevant decisions/timeline/current state/registries, then close the active Issue. `PDPONE END` is the explicit user command for this closure workflow.
