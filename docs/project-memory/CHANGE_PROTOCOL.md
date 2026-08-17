# PDP One — Change Protocol

## 1. Activation

A project mutation session exists only when the user's operational request starts with:

`PDPONE START`

Otherwise the conversation remains read-only/advisory.

## 2. START Context Sync

Read:

- `PDP-ONE-START-HERE.md`
- Manifest / Current State
- System of Record / Live Source Registry
- Guardrails
- Multi-Chat Coordination
- Current Backlog
- active decisions
- relevant domain documentation
- active Session Issues
- open PRs
- latest relevant live state

Result must be PASS before normal writes.

## 3. Create a Session record

Before first project write:

- create a GitHub Session Issue;
- record exact starting `main`;
- declare scope/soft locks;
- record relevant live state and known conflicts;
- create an independent branch.

## 4. PRE-WRITE sync

Immediately before material source/config/schema/automation writes:

- refresh `main`;
- refresh active sessions/PRs;
- verify no new overlap;
- update the Session Issue if scope changed.

## 5. Implementation

Use the smallest safe change consistent with current architecture. Preserve established working behavior unless the user explicitly requests redesign.

For each material milestone, record:

- investigation/root cause
- decision
- commit/head
- tests/CI
- new blockers

## 6. Development-fast deployment

For ordinary active development:

`Branch → CI → immutable exact images → exact-commit deploy → health → merge`

Do not locally build application images.

The exact deploy head is tracked independently from the eventual merge SHA.

Once a deployment returns a Request ID:

- do not issue a duplicate deploy;
- poll/report that exact request;
- treat transient MCP restart disconnects as indeterminate until the exact request is checked.

Development-fast does not have automatic rollback.

## 7. Standard/guarded mode

Historical standard gates may additionally require Preview, final backup, isolated restore verification and explicit approval. Use this mode only when the active workflow/risk/user request requires it.

## 8. PRE-DEPLOY sync

Before deployment:

- refresh `main` and branch/head;
- check concurrent deployment sessions;
- verify CI/image artifacts for the exact head;
- verify Deployment Agent queue/disk state;
- verify any current prerequisite runtime facts.

Do not deploy stale/unverified code.

## 9. Post-deploy verification

- follow exact deployment request to terminal state;
- run independent health when required;
- read relevant live system/data state;
- distinguish a healthy runtime from proof that the intended build is active;
- record exact deployed commit/deployment ID/health evidence.

## 10. PRE-MERGE sync

Immediately before merge:

- refresh `main`;
- inspect active session Issues and open PRs;
- reconcile any change since branch start;
- verify required deploy/health/data evidence;
- ensure memory/decision/session documentation is updated.

## 11. Merge

Merge only after the applicable gates pass.

Keep separately:

- starting base SHA
- PR head SHA
- exact deployed SHA
- merge SHA

## 12. Post-merge memory sync

Update as applicable:

- Session Log
- Timeline
- Decision Register/ADR
- Deployment/Incident history
- Current State
- Backlog
- Automation Registry/specs
- Live Source/Resource Registry
- Manifest

Then close the Session Issue.

## 13. Definition of done

A change is done only when:

`Implementation + Verification + Deployment evidence when applicable + Memory Sync + Session closure`

## 14. Special change classes

### Automation change
Read both GitHub desired spec and live ChatGPT task; detect drift; mutate only in an activated session; verify live after update; immediately sync registry/spec.

### Database migration
Declare DB soft lock; inspect concurrent migrations; preserve business data; never delete data merely to simplify migration.

### Recovery
Refresh backup/runtime/startup architecture; do not replay historical recovery instructions blindly; destructive actions need separate explicit authorization.

### Context/analysis policy
Treat global analysis Context/Prompt/qualifications as high-impact shared resources. Record version/hash and prevent concurrent uncoordinated changes.
