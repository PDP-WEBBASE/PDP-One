# PDP One — Change Protocol

## 1. Conversation activation

A fresh ChatGPT Conversation may mutate PDP One only after the user activates:

`PDPONE START`

Activation is **per Conversation**, not per message and not per individual PR/work item.

After the first successful START Context Sync, the Conversation remains operationally active for later PDP One requests without repeating the keyword. Completing a Work Session/PR does not deactivate the Conversation.

`PDPONE END` explicitly finalizes applicable memory/session closure and deactivates mutation mode in that Conversation. A new Conversation always needs its own first `PDPONE START`.

## 2. Initial START Context Sync

On first activation in a Conversation, read the compact Tier-0/Tier-1 canonical context defined by `PDP-ONE-START-HERE.md` and `MEMORY_RETENTION_AND_COMPACTION.md`:

- Manifest / Current State
- System of Record / Live Source Registry
- Guardrails
- Multi-Chat Coordination
- Current Backlog
- active/relevant decisions
- relevant domain summary
- active Session Issues
- relevant open PRs
- relevant live state

Do not read all historical Session Logs/source archives by default.

Result must be PASS before normal writes.

## 3. Establish the Conversation baseline

After START, retain a lightweight baseline:

- current `main` SHA;
- Project Memory schema/memory version;
- active Session Issues and relevant PR heads;
- relevant decisions/domain docs already loaded;
- relevant Runtime/Automation versions when needed.

This cached baseline accelerates later requests but is never authoritative over GitHub/Runtime/Automation live sources.

## 4. Work Session record

Conversation activation and a GitHub Work Session are separate.

Before the first write of each new material change/workstream:

- run the applicable Delta/Concurrency Check;
- create a GitHub Session Issue;
- record exact starting `main`;
- declare scope/soft locks;
- record relevant live state and known conflicts;
- create an independent branch.

One activated Conversation can complete multiple sequential Work Sessions without asking for `PDPONE START` again.

## 5. Delta Sync for later requests

After the initial START, follow `coordination/DELTA_SYNC_PROTOCOL.md`.

Before later instructions/checkpoints, first compare the cached baseline against:

- current `main` SHA;
- active Session Issues/heartbeats;
- relevant open PR heads;
- only the Runtime/Automation live facts needed by the requested action.

If nothing relevant changed, reuse existing context.

If something changed, read only the relevant commits/diffs/issues/decisions/domain docs and patch the baseline.

Full Project Memory reload is exceptional, not routine.

## 6. PRE-WRITE delta checkpoint

Immediately before material source/config/schema/automation writes:

- refresh `main`;
- refresh active sessions/PRs;
- compare new deltas with lock scope;
- load only relevant changed context;
- update the Session Issue if scope changed.

## 7. Implementation

Use the smallest safe change consistent with current architecture. Preserve established working behavior unless the user explicitly requests redesign.

For each material milestone, record compactly:

- investigation/root cause
- decision and rationale
- commit/head
- tests/CI
- new blockers

Do not paste large raw logs/diffs into memory when exact evidence can be referenced.

## 8. Development-fast deployment

For ordinary active development:

`Branch → CI → immutable exact images → exact-commit deploy → health → merge`

Do not locally build application images.

The exact deploy head is tracked independently from the eventual merge SHA.

Once a deployment returns a Request ID:

- do not issue a duplicate deploy;
- poll/report that exact request;
- treat transient MCP restart disconnects as indeterminate until the exact request is checked.

Development-fast does not have automatic rollback.

## 9. Standard/guarded mode

Historical standard gates may additionally require Preview, final backup, isolated restore verification and explicit approval. Use this mode only when the active workflow/risk/user request requires it.

## 10. PRE-DEPLOY delta checkpoint

Before deployment:

- refresh `main` and branch/head;
- check concurrent deployment sessions;
- read relevant deltas since the last checkpoint;
- verify CI/image artifacts for the exact head;
- verify Deployment Agent queue/disk state;
- verify current prerequisite Runtime facts.

Do not deploy stale/unverified code.

## 11. Post-deploy verification

- follow exact deployment request to terminal state;
- run independent health when required;
- read relevant live system/data state;
- distinguish a healthy runtime from proof that the intended build is active;
- record exact deployed commit/deployment ID/health evidence.

## 12. PRE-MERGE delta checkpoint

Immediately before merge:

- refresh `main`;
- inspect active Session Issues and relevant open PRs;
- compare/reconcile changes since the last baseline;
- load only overlapping/dependency-relevant deltas;
- verify required deploy/health/data evidence;
- ensure memory/decision/session documentation is updated.

## 13. Merge

Merge only after the applicable gates pass.

Keep separately:

- starting base SHA
- PR head SHA
- exact deployed SHA
- merge SHA

## 14. Post-merge memory sync

Update only the canonical records affected by the change:

- Session Log
- Timeline/event index when material
- Decision Register/ADR when a decision changed
- Deployment/Incident history when applicable
- Current State when current truth changed
- Backlog
- Automation Registry/specs when applicable
- Live Source/Resource Registry when applicable
- compact domain summary when accepted behavior changed
- Manifest when routing/schema/governance changed

Then close the Work Session Issue.

Do not append repetitive run/log detail into active files.

## 15. Memory retention/compaction

Follow `MEMORY_RETENTION_AND_COMPACTION.md`.

- Tier 0/1 remains compact.
- Tier 2 domain summaries are lazy-loaded by domain.
- Tier 3 history is loaded only for rationale/regression/audit.
- Tier 4 source/evidence is loaded only when needed.
- Raw high-volume datasets/logs/automation payloads stay in their authoritative systems.
- Material changes preserve reasoning/provenance without copying entire transcripts or telemetry.

## 16. Definition of done

A Work Session change is done only when:

`Implementation + Verification + Deployment evidence when applicable + Memory Sync + Session closure`

Work Session closure does not deactivate the Conversation unless the user explicitly uses `PDPONE END`.

## 17. Special change classes

### Automation change
Read both GitHub desired spec and live ChatGPT task; detect drift; mutate only in an activated Conversation with a scoped Work Session; verify live after update; sync registry/spec. Routine successful run payloads are not copied into Git history.

### Database migration
Declare DB soft lock; inspect concurrent migrations; preserve business data; never delete data merely to simplify migration.

### Recovery
Refresh backup/runtime/startup architecture; do not replay historical recovery instructions blindly; destructive actions need separate explicit authorization.

### Context/analysis policy
Treat global analysis Context/Prompt/qualifications as high-impact shared resources. Record version/hash and prevent concurrent uncoordinated changes.