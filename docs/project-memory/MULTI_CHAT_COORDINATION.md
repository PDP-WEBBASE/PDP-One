# PDP One — Multi-Chat Coordination

PDP One may be changed by more than one ChatGPT Conversation at the same time. GitHub is the shared coordination plane.

## Conversation activation versus Work Session

A new ChatGPT Conversation enters PDP One mutation mode only after its first `PDPONE START`.

After successful START Context Sync, that **Conversation remains activated** for later PDP One requests without repeating the keyword. This activation persists across multiple sequential GitHub Work Sessions in the same Conversation.

A **Work Session** is a scoped GitHub Issue/branch/PR workstream. It is not the same thing as Conversation activation.

`PDPONE END` explicitly deactivates the Conversation after applicable memory/session closure. Closing one Work Session alone does not deactivate it.

## Work Session lifecycle

After activation and before the first write of each new material workstream, create a GitHub Session Issue with:

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

If dedicated labels are unavailable, open Issues whose titles start with `[PDP SESSION]` are the mandatory discovery fallback.

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

## Initial START versus later checkpoints

### Initial START — once per Conversation
Before the first PDP One mutation work in that Conversation:
- read compact canonical Tier-0/Tier-1 memory;
- read current `main`;
- read active Session Issues;
- read relevant open PRs;
- refresh only relevant Runtime/Automation state;
- establish the Conversation baseline.

Do not load raw historical archives by default.

### PRE-WRITE / PRE-DEPLOY / PRE-MERGE
After activation, these are **Delta Sync checkpoints**. Follow `coordination/DELTA_SYNC_PROTOCOL.md`.

At each checkpoint:
- compare previous baseline `main` with current `main`;
- check active Session Issue heartbeats;
- check relevant PR head SHAs/changed files;
- refresh only the live facts needed for the risk boundary;
- load only changed context that overlaps or materially affects current scope.

Do not reload full Project Memory merely because a checkpoint occurs.

## Cheap cross-chat change detection

A conversation can detect other-chat work without rereading history by checking:

- current `main` SHA;
- open `[PDP SESSION]` Issues and their latest phase/heartbeat;
- relevant open PR head SHAs and changed filenames;
- deployment/automation/runtime state only when the current request depends on it.

If these relevant fingerprints have not changed, reuse the cached Conversation context.

## When another chat changes `main`

If `main` changed after the last baseline:

1. compare previous baseline SHA → new `main`;
2. identify the responsible commit/PR/session;
3. inspect changed filenames;
4. read only changes intersecting the current scope or shared dependencies;
5. reconcile/rebase/test if required;
6. advance the baseline to the new `main`.

Unrelated changes do not require loading their full domain history.

## When another chat changes unmerged work

If `main` did not change but another active Session/PR did:

1. inspect that Issue heartbeat and new PR head/changed filenames;
2. compare its soft lock against the current Work Session;
3. load only overlap/dependency-relevant information;
4. continue if unrelated;
5. resolve overlap before conflicting writes/deploys/merges.

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
- same core governance/safety file

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

Keep heartbeat text compact. Link exact PR/commit/request/evidence instead of copying long logs.

## Full context reload is exceptional

A broader reload is appropriate only when:

- core governance/safety/source-precedence semantics changed;
- memory schema changed incompatibly;
- a major architecture/domain redesign invalidated cached assumptions;
- the baseline cannot be reliably reconciled;
- the relevant delta is too large to safely patch selectively;
- the user explicitly requests full resync/audit.

Even then, historical source archives remain lazy-loaded unless relevant.

## Interrupted chats

If a Work Session ends unexpectedly, leave its Issue open with the latest known:

- commit/branch
- CI state
- deployment Request ID if any
- pending operation
- blocker
- next action

A new Conversation may resume it only after its own `PDPONE START`, Context Sync and conflict check.

## Closing a Work Session

A successful Work Session must produce/update a permanent Session Log in `docs/project-memory/history/sessions/`, sync only relevant decisions/timeline/current state/registries/domain summaries, then close the active Issue.

The Conversation remains activated for later PDP One requests unless the user explicitly sends `PDPONE END`.