# PDP ONE — START HERE

> **STOP — PDP One mutation mode must first be activated with `PDPONE START` in each new Conversation. Once activated successfully, do not require the keyword again for later requests in the same Conversation.**

This file is the mandatory entry point for every ChatGPT conversation, developer, recovery session, deployment session, automation-maintenance session, and project change affecting PDP One.

## 1. Conversation activation gate

`PDPONE START` is required **once per new ChatGPT Conversation**, not once per user instruction and not once per individual PR/work session.

Rules:

- A fresh Conversation is READ-ONLY / ADVISORY until the user activates `PDPONE START`.
- After a successful START Context Sync, mark the Conversation activation state `ACTIVE`.
- While that same Conversation remains active, later PDP One requests do **not** require another `PDPONE START`.
- Completing/closing one GitHub Session Issue or PR does not deactivate the Conversation; a later change in the same Conversation may create a new work Session after a Delta Sync.
- `PDPONE END` explicitly performs final memory/session closure as applicable and deactivates mutation mode for that Conversation. A later mutation in the same Conversation then requires a new `PDPONE START`.
- A brand-new Conversation always requires its own first `PDPONE START`.

Without an active Conversation, do not create branches, commits, PRs, server writes, database writes, deployments, recovery mutations, token rotations, or ChatGPT Automation changes.

Activation does **not** bypass safety. Destructive recovery, token rotation, volume operations, or other specially guarded actions still require their own explicit authorization.

## 2. Fresh-chat bootstrap

The minimal product-level bootstrap is defined in:

`PDP-ONE-CHATGPT-BOOTSTRAP.md`

It exists only to teach a fresh chat what `PDPONE START` means, which repository to open (`PDP-WEBBASE/PDP-One`), and that this file is the entry point. It must not duplicate project history.

## 3. Initial START Context Sync — once per Conversation

On the first `PDPONE START` in a Conversation, build a compact canonical baseline. Read/reconcile:

1. `docs/project-memory/MANIFEST.json`
2. `docs/project-memory/CURRENT_STATE.md`
3. `docs/project-memory/SYSTEM_OF_RECORD_MATRIX.md`
4. `docs/project-memory/live-sources/LIVE_SOURCE_REGISTRY.md`
5. `docs/project-memory/SECURITY_AND_SAFETY_GUARDRAILS.md`
6. `docs/project-memory/MULTI_CHAT_COORDINATION.md`
7. `docs/project-memory/CURRENT_BACKLOG.md`
8. active/relevant decisions from `docs/project-memory/decisions/DECISION_REGISTER.md`
9. all open PDP Session Issues / active-work records
10. all open relevant PRs
11. relevant Tier-2 domain summaries
12. only the live sources needed for the current request

Do **not** load raw historical archives, all Session Logs, all diagnostics, or all evidence merely because the project is activated. Follow `docs/project-memory/MEMORY_RETENTION_AND_COMPACTION.md`.

Do not substitute historical snapshots for live verification.

## 4. Conversation baseline

After successful START, retain a per-Conversation working baseline including at least:

- activation state = ACTIVE;
- current GitHub `main` SHA;
- Project Memory schema/memory version;
- canonical/relevant decisions already loaded;
- active Session Issues and relevant PR heads;
- current work Session/branch/PR if one exists;
- relevant Runtime or Automation versions/state only when the current work depends on them.

This baseline is a cache, never a system of record.

## 5. Later requests in the same Conversation — Delta Sync

For every later request, use:

`docs/project-memory/coordination/DELTA_SYNC_PROTOCOL.md`

Do a lightweight change detector first. If nothing relevant changed, reuse the already-loaded context. If another chat changed GitHub or an active PR/Session, read only the relevant delta and patch this Conversation's context.

Do **not** repeatedly reload the full Project Memory.

Required risk checkpoints after initial START are Delta Sync checkpoints:

- PRE-WRITE
- PRE-DEPLOY
- PRE-MERGE

A broader/full canonical reload is reserved for material governance/schema/architecture changes, unreconcilable baseline drift, very large relevant deltas, or an explicit full-resync request.

## 6. Required status before write

Initial activation report:

```text
PDP One Context Sync
Conversation activation: ACTIVE
Canonical memory: PASS / INCOMPLETE
GitHub main: <sha>
Runtime: VERIFIED / NOT REQUIRED / UNVERIFIED
Automations: VERIFIED / NOT REQUIRED / UNVERIFIED
Active sessions: <n>
Open PRs: <n>
Relevant decisions: <ids>
Concurrency: CLEAR / OVERLAP
Result: PASS / CONFLICT / INCOMPLETE
```

Later requests may use the smaller Delta Sync report defined in `DELTA_SYNC_PROTOCOL.md`.

Only `PASS` permits normal project writes. Resolve `CONFLICT`/`INCOMPLETE` first for risky changes.

## 7. Work Session versus Conversation activation

These are different concepts:

- **Conversation activation**: one `PDPONE START` enables PDP One mutation mode for the same ChatGPT Conversation.
- **Work Session**: a GitHub Issue/branch/PR scope for one material change or coordinated workstream.

One activated Conversation may complete multiple sequential Work Sessions without asking the user to repeat `PDPONE START`.

Before the first write of each new material Work Session, create/refresh a PDP Session Issue, declare scope/soft locks, and run the applicable Delta/Concurrency Sync.

## 8. Multi-chat rule

Other conversations may change PDP One concurrently. Check active sessions and `main` at the required checkpoints.

If another chat overlaps, use Split, Sequence, Integrate, Rebase/Refresh, or explicit user-approved conflict acceptance. Never proceed blindly.

If another chat changed unrelated files/domain state, advance the baseline without loading unrelated history.

## 9. Source-of-truth rule

- GitHub: source code, canonical memory, decisions, historical evidence, desired configuration and change coordination.
- PDP One Runtime/Server: live application, database, deployment-agent and operational state.
- ChatGPT Automations: live scheduled-task execution state.
- Historical transfer packages: immutable evidence of what was known at a particular time, **not current state**.

## 10. Memory/read-efficiency rule

Follow `docs/project-memory/MEMORY_RETENTION_AND_COMPACTION.md`:

- Tier 0/1 stays compact and routine-readable;
- domain summaries are loaded only when relevant;
- detailed history/evidence is lazy-loaded;
- raw high-volume logs/data do not accumulate in normal Git history;
- summaries link to exact decisions/sessions/PRs/evidence instead of copying large payloads.

## 11. Exact-version rule

Always keep these separate:

- GitHub `main`
- PR head commit
- merge commit
- deployed exact commit
- deployment ID
- image/build identity

Never infer deployed identity from a merge SHA.

## 12. Definition of done

`Code done != Project done`.

A project change is complete only after implementation/verification, deployment evidence when applicable, canonical memory update, and Work Session closure.

Closing a Work Session does not automatically deactivate the Conversation.

## 13. Bootstrap prompt for future chats

> In a new Conversation, require `PDPONE START` once before PDP One mutations. After successful activation, keep that Conversation active and do not require the keyword again for later PDP One requests unless the user explicitly used `PDPONE END`. Open repository `PDP-WEBBASE/PDP-One`, read `PDP-ONE-START-HERE.md`, build the compact initial baseline, then use Delta Sync for subsequent requests instead of reloading full history. Refresh dynamic information only from authoritative sources, check active GitHub sessions/PRs before writes, record material decisions/change rationale/evidence, never store secrets, and load detailed history/evidence only when relevant.